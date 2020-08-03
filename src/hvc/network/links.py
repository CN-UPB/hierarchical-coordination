class InterDomainLink:
    """ Defines an (undirected) link between the border nodes of two domains over which traffic can be routed """


def __init__(
        self, delay, data_rate,
        start_domain, end_domain,
        start_identifier, end_identifier):
    """
    Initializes an inter domain link.
    :param self:
    :param delay: The annotated delay along the link
    :param data_rate: The annotated rate along the link
    :param start_domain: The domain of the starting node
    :param end_domain: The domain of the ending link
    :param start_identifier: An identifier for a node in the starting domain.
    When a node is connected to multiple domains, the same identifier has to be used.
    :param end_identifier:  An identifier for a node in the ending domain.
    :return:
    """
    self.delay = delay
    self.data_rate = data_rate
    self.start_domain = start_domain
    self.end_domain = end_domain
    self.start_identifier = start_identifier
    self.end_identifier = end_identifier

class IntraDomainPath:
    """
    Defines a path between two border nodes within a domain.
    Alongside this path chains of VNFs can be placed and traffic can be routed.
    """
def __init__(
        self, delay, data_rate,
        start_node, end_node,
        cpu, identifier):
    self.delay = delay
    self.data_rate = data_rate
    self.start_node = start_node
    self.end_node = end_node
    self.cpu = cpu
    self.identifier = identifier
