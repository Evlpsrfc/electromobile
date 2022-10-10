"""Electro Mobile Charging Assistant of Soochow University

Actually, this backend acts like a relay server. It accepts requests
from users and forwards them to the real destination, thus allowing
users to access parts of the backend without knowing the username or
password, and also protecting the backend from attacks.

For security reasons, the backend address is omitted in the open source
code, as is part of the payload body. However, in order to facilitate
debugging by secondary developers, an interface has been opened for
access to the original information from the backend (no need to log in
on the developer side).
"""

from collections import defaultdict
import json

from flask import Flask, render_template, redirect, request
import requests
from waitress import serve


app = Flask(__name__)
session = requests.Session()
# NOTE: target url is omitted for security
base_url = ""
# TODO: load the data below more flexibly
regions = {
    # 独墅湖
    "DSH": ["DSH104", "DSH109", "DSH201", "DSHB02", "DSHB04", "DSHSTX"],
    # 天赐庄
    "TCZ": ["BBNS", "DWQ", "ND07", "SH07", "WSL", "YFL"],
    # 阳澄湖
    "YCH": ["YCH1B", "YCH1C", "YCHST"],
}
shed_names = {
    # TODO: more easily understood alias
    # 独墅湖
    "DSH104": "104号楼", "DSH109": "109号楼", "DSH201": "201号楼",
    "DSHB02": "B02号楼", "DSHB04": "B04号楼", "DSHSTX": "食堂西北角",
    # 天赐庄
    "BBNS": "本部女生大院", "DWQ": "东吴桥下", "ND07": "东七宿舍楼",
    "SH07": "本七宿舍楼", "WSL": "文思楼", "YFL": "逸夫楼",
    # 阳澄湖
    "YCH1B": "1B号楼", "YCH1C": "1C号楼", "YCHST": "食堂",
}
host_names = {
    # TODO: complete the correspondence between pos number and its id
    # 逸夫楼
    "01180015": "一号机",
    # 独墅湖校区104号楼
    "01180019": "一号机",
    # 东吴桥下
    "01180027": "三号机", "01180093": "一号机 (不支持扫码支付)", "01180168": "二号机",
    # 独墅湖校区201号楼
    "01180033": "一号机",
    # 本七宿舍楼
    "01180043": "一号机", "01180089": "三号机", "01180135": "二号机",
    # 东七宿舍楼
    "01180044": "二号机", "01180045": "一号机",
    # 本部女生大院
    "01180051": "一号机",
    # 文思楼
    "01180064": "一号机", "01180094": "二号机",
    # 独墅湖校区109号楼
    "01180117": "一号机",
    # 独墅湖校区食堂
    "01180126": "一号机",
    # 阳澄湖校区1C
    "01180196": "一号机",
}


@app.route("/login/createImage")
def createImage():
    r = session.get("{}/login/createImage".format(base_url))
    return r.content


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        # check if logged in, if not, then login, otherwise redirect
        r = session.get(url="{}/index".format(base_url), allow_redirects=False)
        if r.status_code == 200:
            return redirect("/")
        return render_template("login.html")
    session.post(
        url="{}/login".format(base_url),
        data={
            # NOTE: some payload here is omitted for security
            "username": "",
            "password": "",
            "verifyCode": request.form["verifyCode"],
        }
    )
    return redirect("/")


@app.route("/")
def index(region_id=None):
    r = session.post(
        url="{}/pos/getDeviceStatus".format(base_url),
        data={
            "regionNum": "JSSZ",
            "housingEstateNum": "SZDX",
            "deviceNum": "all",
            "cdpNum": "all",
        }
    )
    if r.headers["Content-Type"] != "application/json":
        return redirect("/login")
    region_id = request.args.get("region", "TCZ")
    if region_id not in ["DSH", "TCZ", "YCH"]:
        return "Illegal query parameter", 400
    data = parse_data(r.json()["data"], region_id)
    return render_template("index.html", data=data, region=region_id)


@app.route("/pos/getDeviceStatus", methods=["POST"])
def getDeviceStatus():
    """Interface only for those who want to do secondary development"""
    r = session.post(
        url="{}/pos/getDeviceStatus".format(base_url),
        data={
            "regionNum": "JSSZ",        # 江苏苏州
            "housingEstateNum": "SZDX", # 苏州大学
            "deviceNum": request.form["deviceNum"], # could be "all" or keys in `shed_names`
            "cdpNum": request.form["cdpNum"],       # could be "all" or keys in `host_names`
        }
    )
    if r.headers["Content-Type"] != "application/json":
        # set code to 1, meaning not logged in
        return '{"total": 0, "code": 1, "data": []}'
    return r.content


def parse_data(raw_data, region_id):
    """keys in raw data:
    cdpbh: 充电棚编号
    posbh: POS机编号
    czbh: 插座编号
    czzt: 插座状态
    sfzx: 是否在线
    """
    renamed_data = [{
        "shed_id": item["cdpbh"],
        "host_id": item["posbh"],
        "socket_id": item["czbh"],
        "status": int(item["czzt"]) if item["sfzx"] else 3,
    } for item in raw_data if item["cdpbh"] in regions[region_id]]
    with open("broken-sockets.json") as f:
        broken_sockets = json.load(f)
    for item in renamed_data:
        if item["status"] == 0 and item["socket_id"] in broken_sockets.get(item["host_id"], []):
            item["status"] = 3
    recursive_defaultdict = lambda: defaultdict(recursive_defaultdict)
    nested_data = recursive_defaultdict()
    for item in renamed_data:
        nested_data[item["shed_id"]][item["host_id"]][item["socket_id"]] = item["status"]
    data = [{
        "id": shed_id,
        "name": shed_names.get(shed_id, shed_id),
        "hosts": [{
            "id": host_id,
            "name": host_names.get(host_id, host_id),
            "sockets": [{
                "id": socket_id,
                "status": socket_info,
            } for socket_id, socket_info in host_info.items()]
        } for host_id, host_info in shed_info.items()]
    } for shed_id, shed_info in nested_data.items()]
    for shed in data:
        for host in shed["hosts"]:
            host.update({
                "num_standby": sum(1 for socket in host["sockets"] if socket["status"] == 0),
                "num_unbroken": sum(1 for socket in host["sockets"] if socket["status"] != 3),
            })
        shed["hosts"].sort(key=lambda x: (x["num_standby"], x["num_unbroken"]), reverse=True)
        shed.update({
            "num_standby": sum(host["num_standby"] for host in shed["hosts"]),
            "num_unbroken": sum(host["num_unbroken"] for host in shed["hosts"]),
        })
    data.sort(key=lambda x: (x["num_standby"], x["num_unbroken"]), reverse=True)
    return data


if __name__ == "__main__":
    # app.run(debug=True, host="0.0.0.0")
    serve(app, host="0.0.0.0", port=5000)