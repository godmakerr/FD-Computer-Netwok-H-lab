import argparse
import threading
import time
import socket
import hashlib
import os
import traceback
from packet import Packet, FLAG_DATA, FLAG_ACK, FLAG_FIN, FLAG_REQ, FLAG_MD5, MSS
from queue import Queue

SERVER_PORT = 12345

class ReliableUDPClient:
    def __init__(self, server_ip, filename, protocol, congestion_control, operation):
        self.server_address = (server_ip, SERVER_PORT)
        self.filename = filename
        self.protocol = protocol
        self.congestion_control = congestion_control
        self.operation = operation
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(0.1)
        self.lock = threading.Lock()
        self.running = True
        self.md5_verified = False
        self.transfer_complete = False  
        self.expected_seq_num = 0
        self.received_packets = {}
        self.md5_hash = hashlib.md5()
        self.queue = Queue()
        self.md5_received = False
        self.md5_timer = None

        if self.operation == 'upload':
            self.file_data = self.read_file()
            self.total_packets = len(self.file_data)
            self.base = 0
            self.next_seq_num = 0
            self.window_size = 1  
            self.ssthresh = 16
            self.timers = {}
            self.ack_received = {}
            self.RTT_times = {}
            self.alpha = 0.125  # For RTT estimation
            self.beta = 0.25    # For RTT estimation
            self.estimated_RTT = 0.1
            self.dev_RTT = 0.05
            self.timeout_interval = 1.0

            self.total_data_sent = 0  # Total data sent (including retransmissions)
            self.start_time = None
            self.end_time = None
        elif self.operation == 'download':
            self.file = open(f"downloaded_{self.filename}", 'wb')

    def read_file(self):
        data = []
        try:
            with open(self.filename, 'rb') as f:
                while True:
                    chunk = f.read(MSS)
                    if not chunk:
                        break
                    data.append(chunk)
        except FileNotFoundError:
            print(f"File '{self.filename}' not found.")
            data = []
        return data

    def compute_md5(self):
        md5 = hashlib.md5()
        if self.operation == 'upload':
            try:
                with open(self.filename, 'rb') as f:
                    while True:
                        chunk = f.read(4096)
                        if not chunk:
                            break
                        md5.update(chunk)
            except FileNotFoundError:
                print(f"File '{self.filename}' not found for MD5 computation.")
        elif self.operation == 'download':
            try:
                with open(f"downloaded_{self.filename}", 'rb') as f:
                    while True:
                        chunk = f.read(4096)
                        if not chunk:
                            break
                        md5.update(chunk)
            except FileNotFoundError:
                print(f"Downloaded file 'downloaded_{self.filename}' not found for MD5 computation.")
        return md5.hexdigest()

    def run(self):
        if self.operation == 'upload':
            self.start_upload()
            while self.running:
                time.sleep(0.1)
            self.finish_upload()
        elif self.operation == 'download':
            self.start_download()
            while self.running:
                time.sleep(0.1)
            self.finish_download()

    # Upload Methods
    def start_upload(self):
        if not self.file_data:
            print("No data to upload.")
            self.running = False
            return
        self.start_time = time.time()  
        threading.Thread(target=self.send_packets, daemon=True).start()
        threading.Thread(target=self.receive_acks, daemon=True).start()

    def send_packets(self):
        while self.running:
            self.lock.acquire()
            while self.next_seq_num < self.base + self.window_size and self.next_seq_num < self.total_packets:
                if self.next_seq_num not in self.ack_received:
                    payload = self.file_data[self.next_seq_num]
                    packet = Packet(seq_num=self.next_seq_num, payload=payload)
                    self.sock.sendto(packet.to_bytes(), self.server_address)
                    send_time = time.time()
                    self.RTT_times[self.next_seq_num] = send_time
                    self.total_data_sent += len(packet.to_bytes())
                    print(f"Sent packet {self.next_seq_num}")
                    if self.protocol == 'SR':
                        timer = threading.Timer(self.timeout_interval, self.handle_timeout, [self.next_seq_num])
                        self.timers[self.next_seq_num] = timer
                        timer.start()
                    elif self.protocol == 'GBN' and self.base == self.next_seq_num:
                        self.start_timer()
                self.next_seq_num += 1
            self.lock.release()
            time.sleep(0.01)

    def receive_acks(self):
        fin_sent_time = None
        MIN_TIMEOUT = 0.5  
        MAX_TIMEOUT = 5.0  

        while self.running:
            try:
                data, _ = self.sock.recvfrom(1024)
                ack_packet = Packet.from_bytes(data)
                base_before = self.base  
                if ack_packet.flags == FLAG_ACK:
                    self.lock.acquire()
                    ack_num = ack_packet.ack_num
                    if ack_num in self.RTT_times:
                        sample_RTT = time.time() - self.RTT_times[ack_num]
                        self.estimated_RTT = (1 - self.alpha) * self.estimated_RTT + self.alpha * sample_RTT
                        self.dev_RTT = (1 - self.beta) * self.dev_RTT + self.beta * abs(sample_RTT - self.estimated_RTT)
                        self.timeout_interval = self.estimated_RTT + 4 * self.dev_RTT
                        self.timeout_interval = max(MIN_TIMEOUT, min(self.timeout_interval, MAX_TIMEOUT))


                    self.ack_received[ack_num] = True
                    if ack_num in self.timers:
                        self.timers[ack_num].cancel()
                        del self.timers[ack_num]

                    if self.protocol == 'SR':
                        while self.ack_received.get(self.base, False):
                            self.base += 1
                    elif ack_num >= self.base:
                        self.base = ack_num + 1

                    base_after = self.base
                    base_moved = base_after > base_before  

                    print(f"Received ACK {ack_num}, window moves to {self.base}")

                    if self.protocol == 'GBN':
                        self.start_timer()
                    if base_moved:
                        if self.congestion_control == 'loss':
                            self.adjust_window_loss()
                        elif self.congestion_control == 'delay':
                            self.adjust_window_delay()

                    if self.base >= self.total_packets and not self.transfer_complete:
                        print("All packets ACKed. Sending FIN.")
                        fin_packet = Packet(flags=FLAG_FIN)
                        self.sock.sendto(fin_packet.to_bytes(), self.server_address)
                        self.transfer_complete = True
                        fin_sent_time = time.time()
                        self.start_md5_timer()
                    self.lock.release()
                elif ack_packet.flags == FLAG_MD5:
                    self.md5_received = True
                    if self.md5_timer is not None:
                        self.md5_timer.cancel()
                    md5_value = ack_packet.payload.decode('utf-8')
                    self.compare_md5(md5_value)
                    self.running = False

                if self.transfer_complete and fin_sent_time:
                    if time.time() - fin_sent_time > 5:  
                        print("Timeout waiting for MD5 from server.")
                        self.running = False

            except socket.timeout:
                if self.transfer_complete and not self.md5_received:
                    print("MD5 packet not received, resending FIN to request MD5.")
                    fin_packet = Packet(flags=FLAG_FIN)
                    self.sock.sendto(fin_packet.to_bytes(), self.server_address)
                    self.start_md5_timer()
                continue
            except ValueError as ve:
                print(f"Received malformed ACK: {ve}")
            except Exception as e:
                print(f"An error occurred while receiving ACKs: {e}")
                traceback.print_exc()

    def start_md5_timer(self):
        if self.md5_timer is not None:
            self.md5_timer.cancel()
        self.md5_timer = threading.Timer(5.0, self.resend_fin_for_md5)
        self.md5_timer.start()

    def resend_fin_for_md5(self):
        print("Resending FIN to request MD5 checksum.")
        fin_packet = Packet(flags=FLAG_FIN)
        self.sock.sendto(fin_packet.to_bytes(), self.server_address)

    def start_timer(self):
        if hasattr(self, 'timer') and self.timer is not None:
            self.timer.cancel()
        self.timer = threading.Timer(self.timeout_interval, self.handle_timeout)
        self.timer.start()

    def handle_timeout(self, seq_num=None):
        self.lock.acquire()
        if not self.running:
            self.lock.release()
            return
        if self.congestion_control == 'loss':
            self.ssthresh = max(self.window_size // 2, 1)
            self.window_size = 1
            print(f"Timeout: Adjusted ssthresh to {self.ssthresh} and window_size to {self.window_size}")
        if self.protocol == 'GBN':
            print("Timeout occurred: Resending all packets from base")
            self.next_seq_num = self.base
            self.start_timer()
        if self.protocol == 'SR' and seq_num is not None:
            if seq_num < self.total_packets:
                packet = Packet(seq_num=seq_num, payload=self.file_data[seq_num])
                self.sock.sendto(packet.to_bytes(), self.server_address)
                self.total_data_sent += len(packet.to_bytes())
                print(f"Resent packet {seq_num}")
                timer = threading.Timer(self.timeout_interval, self.handle_timeout, [seq_num])
                self.timers[seq_num] = timer
                timer.start()
        self.lock.release()

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

    def finish_upload(self):
        self.end_time = time.time()
        if hasattr(self, 'timer') and self.timer is not None:
            self.timer.cancel()
        for timer in self.timers.values():
            timer.cancel()
        self.sock.close()
        print("File upload completed.")

        if self.md5_verified:
            md5_hash = self.compute_md5()
            self.calculate_performance()
        else:
            print("MD5 checksum verification failed. Transfer unsuccessful.")

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

    def compare_md5(self, received_md5):
        if self.operation == 'upload':
            local_md5 = self.compute_md5()
        else:  
            self.file.flush()
            os.fsync(self.file.fileno())
            local_md5 = self.compute_md5()

        print(f"Local MD5: {local_md5}")
        print(f"Received MD5: {received_md5}")
        if local_md5 == received_md5:
            print("MD5 checksum matches. File transfer successful.")
            self.md5_verified = True
        else:
            print("MD5 checksum does not match! File transfer failed.")
            self.md5_verified = False

    # Download Methods
    def start_download(self):
        self.start_time = time.time()
        threading.Thread(target=self.send_file_request, daemon=True).start()
        threading.Thread(target=self.receive_data, daemon=True).start()

    def send_file_request(self):
        request_packet = Packet(flags=FLAG_REQ, payload=self.filename.encode('utf-8'))
        self.sock.sendto(request_packet.to_bytes(), self.server_address)
        print(f"Sent file request for '{self.filename}'")

    def receive_data(self):
        while self.running:
            try:
                data, _ = self.sock.recvfrom(4096)
                packet = Packet.from_bytes(data)
                if packet.flags == FLAG_DATA:
                    if self.protocol == 'GBN':
                        self.handle_gbn(packet)
                    elif self.protocol == 'SR':
                        self.handle_sr(packet)
                elif packet.flags == FLAG_MD5:
                    md5_value = packet.payload.decode('utf-8')
                    self.compare_md5(md5_value)
                    self.running = False  
                elif packet.flags == FLAG_FIN:
                    print("Received FIN from server.")
                    ack_packet = Packet(ack_num=packet.seq_num, flags=FLAG_ACK)
                    self.sock.sendto(ack_packet.to_bytes(), self.server_address)
                    self.transfer_complete = True  
                else:
                    print(f"Received packet with unknown flags: {packet.flags}")
            except socket.timeout:
                continue
            except ValueError as ve:
                print(f"Received malformed packet: {ve}")
            except Exception as e:
                print(f"An error occurred while receiving data: {e}")
                traceback.print_exc()

    def handle_gbn(self, packet):
        if packet.seq_num == self.expected_seq_num:
            with self.lock:
                self.file.write(packet.payload)
                self.md5_hash.update(packet.payload)
            print(f"Received packet {packet.seq_num}")
            ack_packet = Packet(ack_num=self.expected_seq_num, flags=FLAG_ACK)
            self.sock.sendto(ack_packet.to_bytes(), self.server_address)
            self.expected_seq_num += 1
        else:
            ack_num = max(self.expected_seq_num - 1, 0)
            ack_packet = Packet(ack_num=ack_num, flags=FLAG_ACK)
            self.sock.sendto(ack_packet.to_bytes(), self.server_address)

    def handle_sr(self, packet):
        ack_packet = Packet(ack_num=packet.seq_num, flags=FLAG_ACK)
        self.sock.sendto(ack_packet.to_bytes(), self.server_address)
        if packet.seq_num not in self.received_packets:
            self.received_packets[packet.seq_num] = packet.payload
            print(f"Received packet {packet.seq_num}")
            while self.expected_seq_num in self.received_packets:
                with self.lock:
                    self.file.write(self.received_packets[self.expected_seq_num])
                    self.md5_hash.update(self.received_packets[self.expected_seq_num])
                    del self.received_packets[self.expected_seq_num]
                    self.expected_seq_num += 1

    def finish_download(self):
        if hasattr(self, 'file'):
            self.file.flush()  
            os.fsync(self.file.fileno())  
            self.file.close()
        self.sock.close()
        print("File download completed.")

        if self.md5_verified:
            md5_hash = self.compute_md5()
        else:
            print("MD5 checksum verification failed. Transfer unsuccessful.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('server_ip')
    parser.add_argument('filename')
    parser.add_argument('--protocol', choices=['GBN', 'SR'], required=True)
    parser.add_argument('--congestion', choices=['loss', 'delay'], required=True)
    parser.add_argument('--operation', choices=['upload', 'download'], required=True)
    args = parser.parse_args()

    client = ReliableUDPClient(args.server_ip, args.filename, args.protocol, args.congestion, args.operation)
    client.run()
