from src.hvc.api.graphml import read_hierarchy, __read_graph
import yaml as yaml


def test_scenario_1():
    ingresses, egresses = set(), set()
    scenario = "graph_ml_scenario_1"
    graph_input = "testfiles/{0}/input/atlanta_extended.gml".format(scenario)
    hierarchy_path = "testfiles/{0}/input/hierarchy.yaml".format(scenario)
    vnf_description_path = "testfiles/{0}/input/vnf_descriptions.yaml".format(scenario)
    chain_description_path = "testfiles/{0}/input/chains.yaml".format(scenario)
    vnf_requests_path = "testfiles/{0}/input/vnf_requests.yaml".format(scenario)
    solution_path = "testfiles/{0}/solution".format(scenario)
    output_path = "testfiles/{0}/output".format(scenario)

    graph = __read_graph(graph_input)
    root_coordinator = read_hierarchy(hierarchy_path)

    # collect ingresses and egresses
    with open(vnf_requests_path) as vnf_request_file:
        vnf_requests = yaml.load(vnf_request_file)
        for request_desc in vnf_requests.values():
            ingresses.add(request_desc["ingress"])
            egresses.add(request_desc["egress"])

    # build a hierarchy & compute the paths
    root_coordinator.build_hierarchy(network=graph, vnf_ingresses=list(ingresses), vnf_egresses=list(egresses))
    root_coordinator.compute_advertised_paths()
    root_coordinator.write_network_description(output_path)
    root_coordinator.write_advertised_restriction(output_path)