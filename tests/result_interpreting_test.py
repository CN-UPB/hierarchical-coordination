import src.hvc.mip.gurobipy_mip as gmip
import src.hvc.mip.solution_interpreter as interpreter
import src.hvc.mip.utils as utils
from src.hvc.coordinator.coordinator import *

logger = logging.getLogger()
with open('solution_interpreter.log', 'w'):
    pass
logging.basicConfig(filename='solution_interpreter.log', level=logging.WARN)


def cleanup_domains(scenario, domains):
    files_to_cleanup = ["testfiles/result_interpreting/{0}/{1}/vnf_descriptions.yaml",
                        "testfiles/result_interpreting/{0}/{1}/chains.yaml",
                        "testfiles/result_interpreting/{0}/{1}/vnf_requests.yaml",
                        "testfiles/result_interpreting/{0}/{1}/solution.log",
                        "testfiles/result_interpreting/{0}/{1}/full_solution.log"]
    for domain, file in itertools.product(domains, files_to_cleanup):
        path = file.format(scenario, domain)
        if os.path.exists(path):
            os.remove(path)


def run_scenario(scenario, domains, domain_nodes):
    network_description_file = "testfiles/result_interpreting/{0}/network_description.yaml".format(scenario)
    vnf_description_file = "testfiles/result_interpreting/{0}/vnf_descriptions.yaml".format(scenario)
    chain_description_file = "testfiles/result_interpreting/{0}/chains.yaml".format(scenario)
    advertised_restriction_file = "testfiles/result_interpreting/{0}/advertised_restrictions.yaml".format(scenario)
    vnf_request_description_file = "testfiles/result_interpreting/{0}/vnf_requests.yaml".format(scenario)

    parameters, indices, decision_vars, model = gmip.solve_model(network_description_file=network_description_file,
                                                                 chain_description_file=chain_description_file,
                                                                 vnf_description_file=vnf_description_file,
                                                                 vnf_request_description_file=vnf_request_description_file,
                                                                 advertised_restriction_file=advertised_restriction_file,
                                                                 pretty_print=True,
                                                                 output_file="testfiles/result_interpreting/{0}".format(
                                                                     scenario))
    # make sure that there are only two placed VNFs
    # however for each ingress and each egress there is a placement as well
    interpreter.generate_requests_for_child_coordinators(parameters=parameters, indices=indices,
                                                         decision_variables=decision_vars, model=model,
                                                         path_prefix="testfiles/result_interpreting/{0}/".format(
                                                             scenario))
    for domain in domains:
        ### now solve for D1
        network_description_file_domain = "testfiles/result_interpreting/{0}/{1}/network_description.yaml".format(
            scenario, domain)
        vnf_description_file_domain = "testfiles/result_interpreting/{0}/{1}/vnf_descriptions.yaml".format(scenario,
                                                                                                           domain)
        chain_description_file_domain = "testfiles/result_interpreting/{0}/{1}/chains.yaml".format(scenario, domain)
        advertised_restriction_file_domain = "testfiles/result_interpreting/{0}/{1}/advertised_restrictions.yaml".format(
            scenario, domain)
        vnf_request_description_file_domain = "testfiles/result_interpreting/{0}/{1}/vnf_requests.yaml".format(scenario,
                                                                                                               domain)

        extended_network_description_domain = utils.level1_expansion(
            network_description_file_domain, domain_nodes[domain])

        gmip.solve_model(network_description_file=extended_network_description_domain,
                         chain_description_file=chain_description_file_domain,
                         vnf_description_file=vnf_description_file_domain,
                         vnf_request_description_file=vnf_request_description_file_domain,
                         advertised_restriction_file=advertised_restriction_file_domain,
                         pretty_print=True,
                         output_file="testfiles/result_interpreting/{0}/{1}".format(
                             scenario, domain)
                         )


def test_scenario_simple_teardown():
    cleanup_domains("simple_teardown", ["D1", "D2"])
    run_scenario("simple_teardown", [], {})


def test_scenario_full_path_expansion():
    domain_nodes = {
        "D1": {'v1': 20, 'v2': 7,
               'v3': 10, 'v4': 5},
        "D2": {'v5': 10, 'v6': 9,
               'v7': 20, 'v8': 30,
               'v9': 10},
        "D3": {'v10': 15, 'v11': 5,
               'v12': 10, 'v13': 0,
               'v14': 15, 'v15': 3}
    }
    scenario = "full_path_expansion"
    domains = ["D1", "D2", "D3"]

    cleanup_domains(scenario, domains)

    run_scenario(scenario, domains, domain_nodes)


def test_cleanup_scenario_1():
    scenario = "full_path_expansion"
    domains = ["D1", "D2", "D3"]
    cleanup_domains(scenario, domains)


def test_scenario_3():
    domain_nodes = {
        "D1": {'v1': 20, 'v2': 7,
               'v3': 10, 'v4': 5},
        "D2": {'v5': 10, 'v6': 9,
               'v7': 20, 'v8': 30,
               'v9': 10},
        "D3": {'v10': 15, 'v11': 5,
               'v12': 10, 'v13': 0,
               'v14': 15, 'v15': 3}
    }

    scenario = "scenario_3"
    domains = ["D1", "D2", "D3"]

    cleanup_domains(scenario, domains)

    run_scenario(scenario, domains, domain_nodes)


