from socket import *
from threading import Thread
from datetime import datetime, timezone

# 处理客户端连接的函数
def servergo(client):
    try:
        while True:
            # 接收来自客户端的数据
            message = client.recv(buffer_size)
            if not message:  # 客户端断开连接
                print("Client disconnected.")
                break
            message = message.decode()
            
            # 分割报文，提取数据部分
            message_list = message.split('\r\n')
            data = message_list[-1]
            code = '200 OK'
            
            # 如果没有数据，则返回 501 Not Implemented
            if not data:
                code = '501 Not Implemented'
            
            # 如果收到 '#quit' 则断开该客户端连接
            if data == '#quit':
                break
            
            # 将消息中的字母大小写互换
            datalist = list(data)
            for i in range(len(datalist)):
                if datalist[i].isupper():
                    datalist[i] = datalist[i].lower()
                elif datalist[i].islower():
                    datalist[i] = datalist[i].upper()
            context = ''.join(datalist)
            
            # 格式化当前时间为GMT格式
            GMT_FORMAT = '%a, %d %b %Y %H:%M:%S GMT'
            time_now = datetime.now(timezone.utc).strftime(GMT_FORMAT)
            
            # 构建响应报文
            response = '1.0 ' + code + '\r\nDate: ' + time_now + "\r\n\r\n" + context
            
            # 将响应发送回客户端
            client.send(response.encode())
    
    except Exception as e:
        # 捕获异常并打印错误信息
        print(f"An error occurred: {e}")
    
    finally:
        # 关闭客户端连接
        client.close()

# 服务器地址和端口
addr = ('localhost', 12000)
# 缓冲区大小
buffer_size = 1024

# 创建TCP套接字并设置SO_REUSEADDR选项，防止地址重用问题
s = socket(AF_INET, SOCK_STREAM)
s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)

# 绑定服务器地址并开始监听连接
s.bind(addr)
s.listen(5)

# 服务器主循环，持续等待客户端连接
try:
    while True:
        print("listening on port 12000")
        
        # 接受客户端连接请求
        client, c_addr = s.accept()
        print("connecting to ", c_addr)
        
        # 为每个连接创建一个新的线程处理
        t = Thread(target=servergo, args=(client,))
        t.start()

except KeyboardInterrupt:
    # 捕获 Ctrl+C 终止信号并优雅地关闭服务器
    print("\nServer interrupted by user. Shut down.")

finally:
    # 关闭服务器套接字
    s.close()
