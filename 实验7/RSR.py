from ryu.base import app_manager
from ryu.controller import mac_to_port
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.mac import haddr_to_bin
from ryu.lib.packet import packet
from ryu.lib.packet import arp
from ryu.lib.packet import ethernet
from ryu.lib.packet import ipv4
from ryu.lib.packet import ether_types
from ryu.lib import mac, ip
from ryu.topology import event
from collections import defaultdict
import random


class ProjectControllerRSR(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(ProjectControllerRSR, self).__init__(*args, **kwargs)
        self.datapath_list = {}
        self.switches = []
        self.adjacency = defaultdict(dict)
        self.hosts = {
            '10.0.0.1': (1, 1), '10.0.0.2': (1, 2), '10.0.0.3': (2, 1), '10.0.0.4': (2, 2),
            '10.0.0.5': (3, 1), '10.0.0.6': (3, 2), '10.0.0.7': (4, 1), '10.0.0.8': (4, 2),
            '10.0.0.9': (5, 1), '10.0.0.10': (5, 2), '10.0.0.11': (6, 1), '10.0.0.12': (6, 2),
            '10.0.0.13': (7, 1), '10.0.0.14': (7, 2), '10.0.0.15': (8, 1), '10.0.0.16': (8, 2)
        }

        # 初始化路由表和负载
        self.table = {}
        # 正确初始化 self.load，每一行都是独立的列表
        self.load = [[0] * 21 for _ in range(21)]
        self.path_store = []

    def addr_get(self, dpid: int, dst_ip: str) -> int:
        # 检查 dst_ip 是否存在于 hosts 中
        if dst_ip not in self.hosts:
            # self.logger.error(f"Destination IP {dst_ip} not found in hosts.")
            return None  # 或者返回一个默认端口

        s, port = self.hosts[dst_ip]
        if not (1 <= s <= 8):
            # self.logger.error(f"Switch ID {s} for host {dst_ip} out of expected range.")
            return None  # 或者返回一个默认端口

        s1 = (s + 1) // 2 * 2 + 7
        s2 = s1 + 1

        dest = None

        try:
            if 1 <= dpid <= 8:
                if dpid == s:
                    return port
                dest = (dpid + 1) // 2 * 2 + 7 + random.randint(0, 1)
                if dest > 20:
                    # self.logger.error(f"Computed dest {dest} out of range for dpid {dpid}.")
                    return None

            elif 9 <= dpid <= 16:
                if (s1 <= dpid < s1 + 2):
                    dest = s
                elif dpid % 2 == 0:
                    dest = 19 + random.randint(0, 1)
                else:
                    dest = 17 + random.randint(0, 1)
                if dest > 20:
                    # self.logger.error(f"Computed dest {dest} out of range for dpid {dpid}.")
                    return None

            elif 17 <= dpid <= 18:
                dest = (s + 1) // 2 * 2 + 7
                if dest > 20:
                    # self.logger.error(f"Computed dest {dest} out of range for dpid {dpid}.")
                    return None

            elif 19 <= dpid <= 20:
                dest = (s + 1) // 2 * 2 + 8
                if dest > 20:
                    # self.logger.error(f"Computed dest {dest} out of range for dpid {dpid}.")
                    return None

            else:
                # self.logger.error(f"DPID {dpid} out of expected range.")
                return None  # 或者返回一个默认端口

            # 更新负载
            self.load[dpid][dest] += 1
            self.load[dest][dpid] += 1

            # 检查 adjacency 是否存在
            if dest not in self.adjacency[dpid]:
                # self.logger.error(f"No adjacency entry for dpid {dpid} to dest {dest}.")
                return None  # 或者返回一个默认端口

            return self.adjacency[dpid][dest]

        except IndexError as e:
            # self.logger.error(f"Load index out of range: {e}")
            return None  # 或者返回一个默认端口

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(
                datapath=datapath,
                buffer_id=buffer_id,
                priority=priority,
                match=match,
                instructions=inst
            )
        else:
            mod = parser.OFPFlowMod(
                datapath=datapath,
                priority=priority,
                match=match,
                instructions=inst
            )
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def _switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        # 分析数据包
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]
        if eth.ethertype == ether_types.ETH_TYPE_IP:
            _ipv4 = pkt.get_protocol(ipv4.ipv4)
            src_ip = _ipv4.src
            dst_ip = _ipv4.dst
            pkt_type = 'IP'
        elif eth.ethertype == ether_types.ETH_TYPE_ARP:
            arp_pkt = pkt.get_protocol(arp.arp)
            src_ip = arp_pkt.src_ip
            dst_ip = arp_pkt.dst_ip
            pkt_type = 'ARP'
        else:
            return

        dpid = datapath.id
        self.table.setdefault(dpid, {})
        info = (eth.ethertype, in_port, src_ip, dst_ip)

        # 处理输出消息
        if info in self.table[dpid]:
            out_port = self.table[dpid][info]
        else:
            out_port = self.addr_get(dpid, dst_ip)
            if out_port is None:
                # self.logger.warning(f"Could not determine out_port for dpid {dpid} and dst_ip {dst_ip}. Dropping packet.")
                return  # 无法确定输出端口，丢弃数据包
            self.table[dpid][info] = out_port

            # 监控特定路径
            x = 16
            h_x = f"10.0.0.{x}"
            h_x_4 = f"10.0.0.{(x + 4) % 16 or 16}"  # 确保 0 转换为 16
            h_x_5 = f"10.0.0.{(x + 5) % 16 or 16}"

            # 检查是否是 Hx → H(x+4) 或 Hx → H(x+5)
            if src_ip == h_x and dst_ip in [h_x_4, h_x_5]:
                print(f"Path: {src_ip} -> {dst_ip} via DPID {dpid}")

        # 发送并转发
        actions = [parser.OFPActionOutput(out_port)]

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )
        datapath.send_msg(out)

    @set_ev_cls(event.EventSwitchEnter)
    def switch_enter_handler(self, ev):
        switch = ev.switch.dp
        if switch.id not in self.switches:
            self.switches.append(switch.id)
            self.datapath_list[switch.id] = switch
            # self.logger.info(f"Switch {switch.id} entered.")

    @set_ev_cls(event.EventSwitchLeave, MAIN_DISPATCHER)
    def switch_leave_handler(self, ev):
        switch = ev.switch.dp.id
        if switch in self.switches:
            self.switches.remove(switch)
            del self.datapath_list[switch]
            del self.adjacency[switch]
            # self.logger.info(f"Switch {switch} left.")

    # 获取 fat tree 的邻接矩阵
    @set_ev_cls(event.EventLinkAdd, MAIN_DISPATCHER)
    def link_add_handler(self, ev):
        s1 = ev.link.src
        s2 = ev.link.dst
        self.adjacency[s1.dpid][s2.dpid] = s1.port_no
        self.adjacency[s2.dpid][s1.dpid] = s2.port_no
        # self.logger.info(f"Link added: {s1.dpid} (port {s1.port_no}) <--> {s2.dpid} (port {s2.port_no})")

    @set_ev_cls(event.EventLinkDelete, MAIN_DISPATCHER)
    def link_delete_handler(self, ev):
        s1 = ev.link.src
        s2 = ev.link.dst
        # 异常处理，如果交换机已经被删除
        try:
            del self.adjacency[s1.dpid][s2.dpid]
            del self.adjacency[s2.dpid][s1.dpid]
            # self.logger.info(f"Link deleted: {s1.dpid} <--> {s2.dpid}")
        except KeyError:
            # self.logger.warning(f"Attempted to delete non-existing link: {s1.dpid} <--> {s2.dpid}")
            pass

