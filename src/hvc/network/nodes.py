from collections import defaultdict


class Node:
    """
    A node is either an VNF ingress node or an VNF egress node or a domains border node.
    This class is being used for the expansion of the multigraph.
    """

    def __init__(self, domain):
        self.domain = domain
        self.links = defaultdict(list)

    def add_link_to_domain(self, other_domain, link):
        self.links[other_domain].append(link)


class Domain:
    """
    A domain is a node in the hierarchical network.
    A special case is a domain on level k=0 of the hierarchical network
    in which case the domain is a physical substrate node.
    """

    def __init__(self, level):
        self.level = level
        self.border_nodes = []
        self.vnf_ingresses = []
        self.vnf_egresses = []

    def add_border_node(self):
        node = Node(self)
        self.border_nodes.append(node)
        return node

    def add_vnf_ingress(self):
        node = Node(self)
        self.vnf_ingresses.append(node)
        return node

    def add_vnf_egress(self):
        node = Node(self)
        self.vnf_egresses.append(node)
        return node


class SubstrateNode(Domain):
    """
    A substrate node is a node in the substrate (physical network). In a hierarchical sense this is a domain on level 0.
    Substrate nodes are annotated with a cpu capacity.
    """

    def __init__(self, cpu):
        super.__init__(level=0)
        self.cpu = cpu
