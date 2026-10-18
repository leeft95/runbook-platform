import os

url = "mongodb://nypmdevlo25v:27017/"
mk_path = "\\\\elementcapital.corp\\ecns01\\PM\\Michel Kikano"
root_path = f"{mk_path}\\CODE"
root_path_jm = f"{mk_path}\\Joseph\\Utility_Code"
root_path_jm_eu = f"{mk_path}\\Joseph\\EU_Code"

dashboard_path = f"{mk_path}\\Website\\Dashboard"

root_path_s = "S:\\Michel Kikano\\CODE\\"
root_path_jm_s = "S:\\Michel Kikano\\Joseph\\Utility_Code"
root_path_jm_eu_s = "S:\\Michel Kikano\\Joseph\\EU_Code"

data_path = f"{root_path}\\data"
jupyter_path = f"{root_path}\\jupyter"
output_path = f"{root_path}\\outputs"

html_path = f"{output_path}\\htmls"
csv_path = f"{output_path}\\csvs"
json_path = f"{output_path}\\json"

oil_group = [
    "mkikano@elementcapital.com",
    "rzhao@elementcapital.com",
    "ltrindade@elementcapital.com",
    "lballand@elementcapital.com",
]
oil_group_no_mk = [
    "rzhao@elementcapital.com",
    "ltrindade@elementcapital.com",
    "lballand@elementcapital.com",
]
gas_group = [
    "mkikano@elementcapital.com",
    "jmcphillips@elementcapital.com",
    "rzhao@elementcapital.com",
    "ltrindade@elementcapital.com",
    "lballand@elementcapital.com",
    "caitcheson@elementcapital.com",
]
gas_group_us = [
    "mkikano@elementcapital.com",
    "jmcphillips@elementcapital.com",
    "rzhao@elementcapital.com",
    "ltrindade@elementcapital.com",
    "lballand@elementcapital.com",
]
gas_group_eu = [
    "mkikano@elementcapital.com",
    "rzhao@elementcapital.com",
    "ltrindade@elementcapital.com",
    "lballand@elementcapital.com",
    "caitcheson@elementcapital.com",
]
gas_group_no_mk = [
    "jmcphillips@elementcapital.com",
    "rzhao@elementcapital.com",
    "ltrindade@elementcapital.com",
    "lballand@elementcapital.com",
    "caitcheson@elementcapital.com",
]
macro_group = [
    "mkikano@elementcapital.com",
    "rzhao@elementcapital.com",
    "ltrindade@elementcapital.com",
    "lballand@elementcapital.com",
]
macro_group_no_mk = [
    "rzhao@elementcapital.com",
    "ltrindade@elementcapital.com",
    "lballand@elementcapital.com",
]

quant_group = ["rzhao@elementcapital.com", "ltrindade@elementcapital.com"]

DREMIO_TOKENS = dict(
    ltrindade=os.environ["ECM_DREMIO_TOKEN_LTRINDADE"],
    rzhao=os.environ["ECM_DREMIO_TOKEN_RZHAO"],
    pmlo25_svc=os.environ["ECM_DREMIO_TOKEN_PMLO25_SVC"],
)

default_atom_config = {"rda": {"environment": "prod"}, "lo25_internal": {"environment": "prod_lt"}}
