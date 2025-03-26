from socket import *
from datetime import datetime, timezone

# 服务器地址和端口
addr = ('localhost', 12000)
# 缓冲区大小
buffer_size = 1024

# 创建TCP套接字并连接到服务器
c = socket(AF_INET, SOCK_STREAM)
c.connect(addr)

# 客户端主循环，持续接收用户输入并发送到服务器
while True:
    context = input(">>input:")  # 从用户获取输入
    if context == '#quit':  # 输入 '#quit' 时退出循环并关闭连接
        break
    
    # 格式化当前时间为GMT格式
    GMT_FORMAT = '%a, %d %b %Y %H:%M:%S GMT'
    time_now = datetime.now(timezone.utc).strftime(GMT_FORMAT)

    # 构建自定义的FDUnet协议报文
    data = 'POST / 1.0\r\nDate: ' + time_now + '\r\n\r\n' + context
    
    # 将数据发送到服务器
    c.sendall(data.encode())
    
    # 从服务器接收响应数据
    data = c.recv(buffer_size).decode()
    
    # 打印服务器返回的数据
    print('>>', data)

# 关闭客户端的连接
c.close()
