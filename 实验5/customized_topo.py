from mininet.topo import Topo
from mininet.link import TCLink
from mininet.node import OVSKernelSwitch
from mininet.log import setLogLevel, info

class NoLearnSwitch(OVSKernelSwitch):

    def __init__(self, *args, **kwargs):

        kwargs['failMode'] = 'standalone'
        OVSKernelSwitch.__init__(self, *args, **kwargs)

    def start(self, controllers):
        """启动交换机并添加广播流规则"""
        OVSKernelSwitch.start(self, controllers)
        
        switch_name = self.name

        self.cmd(f"ovs-ofctl del-flows {switch_name}")

        flood_flow = "priority=65535,actions=flood"
        cmd = f"ovs-ofctl add-flow {switch_name} {flood_flow}"
        self.cmd(cmd)

class MyTopo(Topo):
    """自定义拓扑类，包含四个主机和两个交换机"""

    def __init__(self):
        """初始化拓扑"""
        Topo.__init__(self)

        # 添加主机
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')
        h3 = self.addHost('h3')
        h4 = self.addHost('h4')

        # 添加交换机，使用自定义的 NoLearnSwitch 类，并指定使用 OpenFlow13
        s1 = self.addSwitch('s1', cls=NoLearnSwitch, protocols='OpenFlow13')
        s2 = self.addSwitch('s2', cls=NoLearnSwitch, protocols='OpenFlow13')

        # 添加链路并设置带宽、延迟和丢包率
        self.addLink(h1, s1, bw=10, delay='2ms', loss=0)
        self.addLink(h2, s1, bw=20, delay='10ms', loss=0)
        self.addLink(s1, s2, bw=20, delay='2ms', loss=10)
        self.addLink(s2, h3, bw=10, delay='2ms', loss=0)
        self.addLink(s2, h4, bw=20, delay='10ms', loss=0)

# 定义 topos 字典，供 Mininet 识别
topos = { 'mytopo': (lambda: MyTopo()) }

