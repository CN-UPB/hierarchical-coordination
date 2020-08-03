import matplotlib.pyplot as plt

import src.hvc.api.graphml as gml
import src.hvc.experiments.result_interpreter as ri
import src.hvc.mip.gurobipy_mip as gmip
from src.hvc.coordinator.coordinator import *


def run_scenario(scenario, to=-1):
    graph_input = "testfiles/{0}/input/atlanta_extended.gml".format(scenario)
    hierarchy_path = "testfiles/{0}/input/hierarchy.yaml".format(scenario)
    vnf_description_path = "testfiles/{0}/input/vnf_descriptions.yaml".format(scenario)
    chain_description_path = "testfiles/{0}/input/chains.yaml".format(scenario)
    vnf_requests_path = "testfiles/{0}/input/vnf_requests.yaml".format(scenario)
    solution_path = "testfiles/{0}/solution".format(scenario)
    output_path = "testfiles/{0}/output".format(scenario)

    gml.solve_graphml_model(graphml_path=graph_input,
                            vnf_description_path=vnf_description_path,
                            chain_description_path=chain_description_path,
                            vnf_request_description_path=vnf_requests_path,
                            output_path=output_path,
                            hierarchy_path=hierarchy_path,
                            max_timeout_delay=to,
                            solution_path=solution_path)

    print(ri.interpret_results(graphml_path=graph_input,
                               vnf_requests_path=vnf_requests_path,
                               hierarchy_path=hierarchy_path,
                               solution_path=solution_path,
                               chains_path=chain_description_path))


# a [1, 2, 4] hierarchy of the atlanta graph
def test_scenario_1():
    scenario = "graph_ml_scenario_1"
    run_scenario(scenario)


# a [1, 3] hierarchy of the atlanta graph
def test_scenario_2():
    scenario = "graph_ml_scenario_2"
    run_scenario(scenario)


# a flat ([1]) hierarchy of the atlanta graph
def test_scenario_3():
    scenario = "graph_ml_scenario_3"
    run_scenario(scenario)


def test_cc_1():
    network_description_file = "testfiles/graph_ml_scenario_1/output/coordinator4/network_description.yaml"
    vnf_description_file = "testfiles/graph_ml_scenario_1/output/coordinator4/vnf_descriptions.yaml"
    chain_description_file = "testfiles/graph_ml_scenario_1/output/coordinator4/chains.yaml"
    advertised_restriction_file = "testfiles/graph_ml_scenario_1/output/coordinator4/advertised_restrictions.yaml"
    vnf_request_description_file = "testfiles/graph_ml_scenario_1/output/coordinator4/vnf_requests.yaml"
    parameters, indices, decision_vars, model = gmip.solve_model(network_description_file=network_description_file,
                                                                 chain_description_file=chain_description_file,
                                                                 vnf_description_file=vnf_description_file,
                                                                 vnf_request_description_file=vnf_request_description_file,
                                                                 advertised_restriction_file=advertised_restriction_file,
                                                                 pretty_print=True)


def test_plot_atalanta():
    scenario = "graph_ml_scenario_1"
    graph_input = "testfiles/{0}/input/atlanta_extended.gml".format(scenario)
    G = nx.DiGraph(nx.read_gml(graph_input))
    nx.draw_networkx(G, pos=nx.spring_layout(G))
    plt.show()
