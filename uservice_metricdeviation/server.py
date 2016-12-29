#!/usr/bin/env python
"""Retrieve QA metrics and report deviation"""
import json
from apikit import APIFlask as apf
from apikit import BackendError
from flask import jsonify, request
from BitlyOAuth2ProxySession import Session


def server(run_standalone=False):
    """Create the app and then run it."""
    # Add "/metric_deviation" for mapping behind api.lsst.codes
    hosturi = "https://squash.lsst.codes"
    app = apf(name="uservice-metricdeviation",
              version="0.0.1",
              repository="https://github.com/sqre-lsst/" +
              "sqre-uservice-metricdeviation",
              description="API wrapper for QA Metric Deviation",
              route=["/", "/metricdeviation"],
              auth={"type": "bitly-proxy",
                    "data": {"username": "",
                             "password": "",
                             "endpoint": hosturi + "/oauth2/start"}})
    app.config["SESSION"] = None

    # Linter can't understand decorators.
    # pylint: disable=unused-variable
    @app.route("/")
    def healthcheck():
        """Default route to keep Ingress controller happy"""
        return "OK"

    @app.route("/<metric>")
    @app.route("/<metric>/<threshold>")
    @app.route("/metricdeviation/<metric>")
    @app.route("/metricdeviation/<metric>/<threshold>")
    def get_metricdeviation(metric, threshold=None):
        """
        Proxy for squash.lsst.codes.  We expect the incoming request to have
        Basic Authentication headers, which will be used to get a GitHub
        Oauth2 token.
        """
        if threshold is None:
            threshold = 0.0
        inboundauth = None
        if request.authorization is not None:
            inboundauth = request.authorization
            currentuser = app.config["AUTH"]["data"]["username"]
            currentpw = app.config["AUTH"]["data"]["password"]
            if currentuser != inboundauth.username or \
               currentpw != inboundauth.password:
                _reauth(app, inboundauth.username, inboundauth.password)
        else:
            raise BackendError(reason="Unauthorized", status_code=403,
                               content="No authorization provided.")
        session = app.config["SESSION"]
        url = hosturi + "/dashboard/api/measurements/"
        params = {"job__ci_dataset": "cfht",
                  "metric": metric,
                  "page": "last"}
        resp = session.get(url, params=params)
        if resp.status_code == 403:
            # Try to reauth
            _reauth(app, inboundauth.username, inboundauth.password)
            session = app.config["SESSION"]
            resp = session.get(url, params)
        if resp.status_code == 200:
            return _interpret_response(resp.text, threshold)
        else:
            raise BackendError(reason=resp.reason,
                               status_code=resp.status_code,
                               content=resp.text)

    @app.errorhandler(BackendError)
    # pylint: disable=unused-variable
    def handle_invalid_usage(error):
        """Custom error handler."""
        response = jsonify(error.to_dict())
        response.status_code = error.status_code
        return response
    if run_standalone:
        app.run(host='0.0.0.0', threaded=True)


def _reauth(app, username, password):
    """Get a session with authentication data"""
    oaep = app.config["AUTH"]["data"]["endpoint"]
    session = Session.Session(oauth2_username=username,
                              oauth2_password=password,
                              authentication_session_url=None,
                              authentication_base_url=oaep)
    session.authenticate()
    app.config["SESSION"] = session


def _interpret_response(inbound, threshold):
    """Decide whether there's a reportable deviation"""
    tval = float(threshold)
    try:
        robj = json.loads(inbound)
    except json.decoder.JSONDecodeError as exc:
        raise BackendError(reason="Could not decode JSON result",
                           status_code=500,
                           content=str(exc) + ":\n" + inbound)
    results = robj["results"]
    retdict = {"changed": False}
    if len(results) < 2:
        # No previous data to compare to!
        return jsonify(retdict)
    prev = results[-2]
    curr = results[-1]
    pval = prev["value"]
    cval = curr["value"]
    if pval != cval:
        if pval:
            delta_pct = abs(100.0 * ((cval + 0.0) - (pval + 0.0)) /
                            (pval + 0.0))
            if delta_pct > tval:
                retdict["changed"] = True
                retdict["current"] = cval
                retdict["previous"] = pval
                retdict["changecount"] = 0
                retdict["delta_pct"] = delta_pct
                ccp = curr["changed_packages"]
                if ccp:
                    retdict["changed_packages"] = ccp
                    retdict["changecount"] = len(ccp)
    return jsonify(retdict)


def standalone():
    """Entry point for running as its own executable."""
    server(run_standalone=True)

if __name__ == "__main__":
    standalone()
