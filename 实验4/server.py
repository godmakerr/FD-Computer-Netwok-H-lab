import threading
import time
import socket
import argparse
import hashlib
import traceback
import heapq
from packet import Packet, FLAG_DATA, FLAG_ACK, FLAG_FIN, FLAG_REQ, FLAG_MD5, MSS
from queue import Queue

SERVER_IP = '0.0.0.0'  # listening on all ports
SERVER_PORT = 12345

class ClientHandler(threading.Thread):
    def __init__(self, sock, client_address, protocol):
        super().__init__(daemon=True)
        self.sock = sock
        self.client_address = client_address
        self.protocol = protocol
        self.expected_seq_num = 0
        self.received_packets = {}
        self.filename = f'received_file_{self.client_address[1]}'  
        self.file = open(self.filename, 'wb')
        self.finished = False
        self.queue = Queue()
        self.lock = threading.Lock()
        self.md5_hash = hashlib.md5()

    def run(self):
        print(f"Started handler for {self.client_address}")
        while not self.finished:
            try:
                data = self.queue.get()
                if not data:
                    continue

                try:
                    packet = Packet.from_bytes(data)
                except ValueError as ve:
                    print(f"Malformed packet from {self.client_address}: {ve}")
                    continue

                if packet.flags == FLAG_DATA:
                    if self.protocol == 'GBN':
                        self.handle_gbn(packet)
                    elif self.protocol == 'SR':
                        self.handle_sr(packet)
                elif packet.flags == FLAG_FIN:
                    print(f"Received FIN from {self.client_address}, closing connection.")
                    ack_packet = Packet(ack_num=packet.seq_num, flags=FLAG_ACK)
                    self.sock.sendto(ack_packet.to_bytes(), self.client_address)
                    self.finished = True
            except Exception as e:
                print(f"An error occurred in handler {self.client_address}: {e}")
                traceback.print_exc()
        self.file.close()
        md5_value = self.md5_hash.hexdigest()
        print(f"MD5 of received file from {self.client_address}: {md5_value}")

        md5_packet = Packet(flags=FLAG_MD5, payload=md5_value.encode('utf-8'))
        self.sock.sendto(md5_packet.to_bytes(), self.client_address)
        print(f"Sent MD5 checksum to {self.client_address}")
        print(f"Connection with {self.client_address} closed.")

    def handle_gbn(self, packet):
        if packet.seq_num == self.expected_seq_num:
            with self.lock:
                self.file.write(packet.payload)
                self.md5_hash.update(packet.payload)
            print(f"Received packet {packet.seq_num} from {self.client_address}")
            ack_packet = Packet(ack_num=self.expected_seq_num, flags=FLAG_ACK)
            self.sock.sendto(ack_packet.to_bytes(), self.client_address)
            self.expected_seq_num += 1
        else:
            ack_num = max(self.expected_seq_num - 1, 0)
            ack_packet = Packet(ack_num=ack_num, flags=FLAG_ACK)
            self.sock.sendto(ack_packet.to_bytes(), self.client_address)

    def handle_sr(self, packet):
        ack_packet = Packet(ack_num=packet.seq_num, flags=FLAG_ACK)
        self.sock.sendto(ack_packet.to_bytes(), self.client_address)
        if packet.seq_num not in self.received_packets:
            self.received_packets[packet.seq_num] = packet.payload
            print(f"Received packet {packet.seq_num} from {self.client_address}")
            while self.expected_seq_num in self.received_packets:
                with self.lock:
                    self.file.write(self.received_packets[self.expected_seq_num])
                    self.md5_hash.update(self.received_packets[self.expected_seq_num])
                    del self.received_packets[self.expected_seq_num]
                    self.expected_seq_num += 1

class FileSender(threading.Thread):
    def __init__(self, sock, client_address, protocol, congestion_control, filename):
        super().__init__(daemon=True)
        self.sock = sock
        self.client_address = client_address
        self.protocol = protocol
        self.congestion_control = congestion_control
        self.filename = filename
        self.md5_hash = hashlib.md5()
        self.file_data = self.read_file()
        self.total_packets = len(self.file_data)
        self.base = 0
        self.next_seq_num = 0
        self.window_size = 4  
        self.ssthresh = 16
        self.ack_received = {}
        self.RTT_times = {}
        self.duplicate_ack_counts = {}
        self.alpha = 0.125
        self.beta = 0.25
        self.estimated_RTT = 0.1
        self.dev_RTT = 0.05
        self.timeout_interval = 1.0
        self.lock = threading.Lock()
        self.running = True
        self.total_data_sent = 0
        self.start_time = None
        self.end_time = None
        self.ack_queue = Queue()
        
        self.timeout_heap = []  
        self.timeout_heap_lock = threading.Lock()

        self.timeout_thread = threading.Thread(target=self.timeout_monitor, daemon=True)
        self.timeout_thread.start()

    def read_file(self):
        data = []
        try:
            with open(self.filename, 'rb') as f:
                while True:
                    chunk = f.read(MSS)
                    if not chunk:
                        break
                    data.append(chunk)
                    self.md5_hash.update(chunk)
        except FileNotFoundError:
            print(f"File '{self.filename}' not found. Cannot send to {self.client_address}.")
            data = []
        return data

    def run(self):
        if not self.file_data:
            print(f"No data to send to {self.client_address}")
            self.running = False
            return
        self.start_time = time.time()
        threading.Thread(target=self.send_packets, daemon=True).start()
        threading.Thread(target=self.process_acks, daemon=True).start()
        while self.running:
            time.sleep(0.1)
        self.finish()

    def send_packets(self):
        while self.running:
            with self.lock:
                while self.next_seq_num < self.base + self.window_size and self.next_seq_num < self.total_packets:
                    if self.next_seq_num not in self.ack_received:
                        payload = self.file_data[self.next_seq_num]
                        packet = Packet(seq_num=self.next_seq_num, payload=payload)
                        self.sock.sendto(packet.to_bytes(), self.client_address)
                        send_time = time.time()
                        self.RTT_times[self.next_seq_num] = send_time
                        self.total_data_sent += len(packet.to_bytes())
                        print(f"Sent packet {self.next_seq_num} to {self.client_address}")

                        timeout_time = send_time + self.timeout_interval
                        with self.timeout_heap_lock:
                            heapq.heappush(self.timeout_heap, (timeout_time, self.next_seq_num))
                        
                        self.next_seq_num += 1
            time.sleep(0.01)

    def process_acks(self):
        while self.running:
            try:
                ack_packet = self.ack_queue.get(timeout=0.1)
                if ack_packet.flags == FLAG_ACK:
                    ack_num = ack_packet.ack_num
                    with self.lock:
                        if ack_num in self.RTT_times:
                            sample_RTT = time.time() - self.RTT_times[ack_num]
                            self.estimated_RTT = (1 - self.alpha) * self.estimated_RTT + self.alpha * sample_RTT
                            self.dev_RTT = (1 - self.beta) * self.dev_RTT + self.beta * abs(sample_RTT - self.estimated_RTT)
                            self.timeout_interval = self.estimated_RTT + 4 * self.dev_RTT

                        if ack_num >= self.base:
                            self.ack_received[ack_num] = True

                            with self.timeout_heap_lock:
                                pass

                            if self.protocol == 'SR':
                                while self.base in self.ack_received and self.ack_received[self.base]:
                                    self.base += 1
                                    if self.base in self.duplicate_ack_counts:
                                        del self.duplicate_ack_counts[self.base]
                            elif ack_num >= self.base:
                                self.base = ack_num + 1

                            print(f"Received ACK {ack_num} from {self.client_address}, window moves to {self.base}")

                            if self.congestion_control == 'loss':
                                self.adjust_window_loss()
                            elif self.congestion_control == 'delay':
                                self.adjust_window_delay()

                            if self.base >= self.total_packets and self.running:
                                print(f"All packets ACKed by {self.client_address}.")
                                self.running = False
                                self.send_md5_and_fin()
                        else:
                            print(f"Received duplicate ACK {ack_num} from {self.client_address}")
                            if self.protocol == 'SR':
                                self.duplicate_ack_counts[ack_num] = self.duplicate_ack_counts.get(ack_num, 0) + 1
                                if self.duplicate_ack_counts[ack_num] == 3:
                                    print(f"Triple duplicate ACK for {ack_num}. Fast retransmit.")
                                    self.handle_fast_retransmit(ack_num)
                elif ack_packet.flags == FLAG_FIN:
                    print(f"Received FIN from {self.client_address}")
                    self.running = False
            except Exception:
                continue

    def receive_ack(self, packet):
        self.ack_queue.put(packet)

    def timeout_monitor(self):
        while self.running:
            current_time = time.time()
            timed_out_packets = []
            with self.timeout_heap_lock:
                while self.timeout_heap and self.timeout_heap[0][0] <= current_time:
                    timeout_time, seq_num = heapq.heappop(self.timeout_heap)
                    if not self.ack_received.get(seq_num, False):
                        timed_out_packets.append(seq_num)
            for seq_num in timed_out_packets:
                self.handle_timeout(seq_num)
            time.sleep(0.05)  

    def handle_fast_retransmit(self, ack_num):
        with self.lock:
            if ack_num < self.total_packets and not self.ack_received.get(ack_num, False):
                packet = Packet(seq_num=ack_num, payload=self.file_data[ack_num])
                self.sock.sendto(packet.to_bytes(), self.client_address)
                send_time = time.time()
                self.RTT_times[ack_num] = send_time
                self.total_data_sent += len(packet.to_bytes())
                print(f"Fast retransmitted packet {ack_num} to {self.client_address}")

                timeout_time = send_time + self.timeout_interval
                with self.timeout_heap_lock:
                    heapq.heappush(self.timeout_heap, (timeout_time, ack_num))

    def handle_timeout(self, seq_num):
        with self.lock:
            if not self.running:
                return
            if self.congestion_control == 'loss':
                self.ssthresh = max(int(self.window_size / 2), 1)
                self.window_size = 1
                print(f"Timeout: Adjusted ssthresh to {self.ssthresh} and window_size to {self.window_size}")
            print(f"Timeout occurred for packet {seq_num}")
            if self.protocol == 'GBN':
                self.base = seq_num + 1
                self.next_seq_num = self.base
                print(f"GBN: Window reset to base {self.base}")
            if self.protocol == 'SR':
                if seq_num < self.total_packets and not self.ack_received.get(seq_num, False):
                    packet = Packet(seq_num=seq_num, payload=self.file_data[seq_num])
                    self.sock.sendto(packet.to_bytes(), self.client_address)
                    send_time = time.time()
                    self.RTT_times[seq_num] = send_time
                    self.total_data_sent += len(packet.to_bytes())
                    print(f"Resent packet {seq_num} to {self.client_address}")

                    timeout_time = send_time + self.timeout_interval
                    with self.timeout_heap_lock:
                        heapq.heappush(self.timeout_heap, (timeout_time, seq_num))

    def adjust_window_loss(self):
        if self.window_size < self.ssthresh:
            self.window_size *= 2
            print(f"Congestion Control (Loss): Window size increased to {self.window_size}")
        else:
            self.window_size += 1
            print(f"Congestion Control (Loss): Window size increased to {self.window_size}")

    def adjust_window_delay(self):
        if not hasattr(self, 'base_RTT'):
            self.base_RTT = self.estimated_RTT
        diff = (self.window_size / self.estimated_RTT) - (self.window_size / self.base_RTT)
        alpha, beta = 1, 3
        if diff < alpha:
            self.window_size += 1
            print(f"Congestion Control (Delay): Window size increased to {self.window_size}")
        elif diff > beta:
            self.window_size = max(1, self.window_size - 1)
            print(f"Congestion Control (Delay): Window size decreased to {self.window_size}")

    def send_md5_and_fin(self):
        md5_value = self.compute_md5()
        md5_packet = Packet(flags=FLAG_MD5, payload=md5_value.encode('utf-8'))
        self.sock.sendto(md5_packet.to_bytes(), self.client_address)
        print(f"Sent MD5 checksum to {self.client_address}")

        fin_packet = Packet(flags=FLAG_FIN)
        self.sock.sendto(fin_packet.to_bytes(), self.client_address)
        print(f"Sent FIN to {self.client_address}")

    def compute_md5(self):
        return self.md5_hash.hexdigest()

    def finish(self):
        self.end_time = time.time()

        md5_value = self.md5_hash.hexdigest()
        md5_packet = Packet(flags=FLAG_MD5, payload=md5_value.encode('utf-8'))
        self.sock.sendto(md5_packet.to_bytes(), self.client_address)
        print(f"Sent MD5 checksum to {self.client_address}")

        fin_packet = Packet(flags=FLAG_FIN)
        self.sock.sendto(fin_packet.to_bytes(), self.client_address)
        print(f"Sent FIN to {self.client_address}")

        print(f"File transfer to {self.client_address} completed.")
        self.calculate_performance()

    def calculate_performance(self):
        file_size = sum(len(chunk) for chunk in self.file_data)
        transfer_time = self.end_time - self.start_time
        effective_throughput = file_size / transfer_time if transfer_time > 0 else 0
        flow_utilization = file_size / self.total_data_sent if self.total_data_sent > 0 else 0

        print(f"\n--- Performance Metrics ---")
        print(f"File size: {file_size} bytes")
        print(f"Transfer time: {transfer_time:.2f} seconds")
        print(f"Effective throughput: {effective_throughput:.2f} bytes/second")
        print(f"Total data sent (including retransmissions): {self.total_data_sent} bytes")
        print(f"Flow utilization rate: {flow_utilization:.4f}")

class ReliableUDPServer:
    def __init__(self, protocol, congestion_control):
        self.server_address = (SERVER_IP, SERVER_PORT)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(self.server_address)
        self.protocol = protocol
        self.congestion_control = congestion_control
        self.client_handlers = {}
        self.file_senders = {}
        self.sender_lock = threading.Lock()

    def start(self):
        print("Server started, waiting for data...")
        while True:
            try:
                data, client_address = self.sock.recvfrom(4096)

                try:
                    packet = Packet.from_bytes(data)
                except ValueError as ve:
                    print(f"Malformed or incomplete packet from {client_address}: {ve}")
                    continue

                if packet.flags == FLAG_REQ:
                    filename = packet.payload.decode('utf-8')
                    print(f"Received file request for '{filename}' from {client_address}")
                    with self.sender_lock:
                        if client_address not in self.file_senders or not self.file_senders[client_address].is_alive():
                            sender = FileSender(self.sock, client_address, self.protocol, self.congestion_control, filename)
                            self.file_senders[client_address] = sender
                            sender.start()
                elif packet.flags in (FLAG_DATA, FLAG_FIN):
                    if client_address not in self.client_handlers or not self.client_handlers[client_address].is_alive():
                        handler = ClientHandler(self.sock, client_address, self.protocol)
                        self.client_handlers[client_address] = handler
                        handler.start()
                    self.client_handlers[client_address].queue.put(data)
                elif packet.flags == FLAG_ACK:
                    with self.sender_lock:
                        if client_address in self.file_senders:
                            self.file_senders[client_address].receive_ack(packet)
                        else:
                            print(f"Received ACK from {client_address} with no active FileSender.")
                else:
                    print(f"Received packet with unknown flags from {client_address}, ignoring.")

                for addr, handler in list(self.client_handlers.items()):
                    if not handler.is_alive():
                        del self.client_handlers[addr]
                for addr, sender in list(self.file_senders.items()):
                    if not sender.is_alive():
                        del self.file_senders[addr]

            except Exception as e:
                print(f"An error occurred in main server: {e}")
                traceback.print_exc()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--protocol', choices=['GBN', 'SR'], required=True)
    parser.add_argument('--congestion', choices=['loss', 'delay'], required=True)
    args = parser.parse_args()

    server = ReliableUDPServer(args.protocol, args.congestion)
    server.start()

if __name__ == '__main__':
    main()
