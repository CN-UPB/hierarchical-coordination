class Parameters:
    def __init__(self, **kwargs):
        self.network_description = kwargs["network_description"]
        self.vnf_description = kwargs["vnf_description"]
        self.chains = kwargs["chains"]
        self.vnf_requests = kwargs["vnf_requests"]
        self.advertised_restrictions = kwargs["advertised_restrictions"]


class DecisionVariables:
    def __init__(self, **kwargs):
        self.lambda_total = kwargs["lambda_total"]
        self.lambda_inter = kwargs["lambda_inter"]
        self.lambda_intra = kwargs["lambda_intra"]
        self.sigma_in = kwargs["sigma_in"]
        self.sigma_out = kwargs["sigma_out"]
        self.delta_inter = kwargs["delta_inter"]
        self.delta_intra = kwargs["delta_intra"]
        self.gamma = kwargs["gamma"]
        self.kappa = kwargs["kappa"]
        self.beta = kwargs["beta"]
        self.epsilon = kwargs["epsilon"]
        self.zeta = kwargs["zeta"]


class Indices:
    def __init__(self, **kwargs):
        self.arcs = kwargs["arcs"]
        self.cpu_restrictions = kwargs["cpu_restrictions"]
        self.paths = kwargs["paths"]
        self.edges = kwargs["edges"]
        self.border_nodes = kwargs["border_nodes"]
        self.vnfs = kwargs["vnfs"]
        self.routing_restrictions = kwargs["routing_restrictions"]


class IntraDomainPath:
    def __init__(self, **kwargs):
        self.identifier = kwargs["identifier"]
        self.source = kwargs["src"]
        self.destination = kwargs["dst"]
        self.domain = kwargs["domain"]
        self.cpu = kwargs["cpu"]
        self.delay = kwargs["delay"]
        self.rate = kwargs["rate"]

    def to_yaml_dict(self):
        return {'src': self.source, 'dst': self.destination,
                'domain': self.domain, 'cpu': self.cpu,
                'delay': self.delay, 'max_rate': self.rate}


class InterDomainLink:
    def __init__(self, **kwargs):
        self.identifier = kwargs["identifier"]
        self.source = kwargs["source"]
        self.destination = kwargs["destination"]
        self.delay = kwargs["delay"]
        self.rate = kwargs["rate"]

    def to_yaml_dict(self):
        return {
            "src": self.source, "dst": self.destination,
            "max_rate": self.rate, "delay": self.delay
        }


class RoutingRestriction:
    def __init__(self, **kwargs):
        self.identifier = kwargs["identifier"]
        self.domain = kwargs["domain"]
        self.paths = kwargs["paths"]
        self.shared_bottleneck = kwargs["shared_bottleneck"]

    def __repr__(self):
        return str(self.to_yaml_dict())

    def to_yaml_dict(self):
        """
        returns a dict that is compatible with the optimization system
        :return:
        """
        return {'domain': self.domain,
                'paths': list(self.paths),
                'shared_bottleneck': self.shared_bottleneck}


class CpuRestriction:
    def __init__(self, **kwargs):
        self.identifier = kwargs["identifier"]
        self.domain = kwargs["domain"]
        self.paths = kwargs["paths"]
        self.shared_cpu = kwargs["shared_cpu"]

    def __repr__(self):
        return str(self.to_yaml_dict())

    def to_yaml_dict(self):
        """
        returns a dict that is compatible with the optimization system
        :return:
        """
        return {'domain': self.domain,
                'paths': list(self.paths),
                'shared_cpu': self.shared_cpu}
