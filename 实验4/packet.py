import struct

MSS = 1024  # 最大分段大小
PACKET_HEADER_FORMAT = '!IIHII'  # struct打包格式

# 数据包标志位
FLAG_DATA = 0
FLAG_ACK = 1
FLAG_FIN = 2
FLAG_REQ = 4
FLAG_MD5 = 8
FLAG_RESULT = 16

class Packet:
    """数据包类，用于创建和解析数据包"""
    def __init__(self, seq_num=0, ack_num=0, flags=FLAG_DATA, window_size=0, payload=b''):
        self.seq_num = seq_num  # 序列号
        self.ack_num = ack_num  # 确认号
        self.flags = flags  # 标志位
        self.window_size = window_size  # 窗口大小
        self.payload = payload  # 负载数据
        self.payload_length = len(payload)  # 负载长度

    def to_bytes(self):
        """将数据包转换为字节流"""
        header = struct.pack(
            PACKET_HEADER_FORMAT,
            self.seq_num,
            self.ack_num,
            self.flags,
            self.window_size,
            self.payload_length
        )
        return header + self.payload  # 拼接头部和负载

    @staticmethod
    def from_bytes(data):
        """从字节流解析出数据包"""
        header_size = struct.calcsize(PACKET_HEADER_FORMAT)
        if len(data) < header_size:
            raise ValueError("Data too short to unpack Packet header.")
        header = data[:header_size]
        seq_num, ack_num, flags, window_size, payload_length = struct.unpack(PACKET_HEADER_FORMAT, header)
        payload = data[header_size:header_size + payload_length]
        return Packet(seq_num, ack_num, flags, window_size, payload)
