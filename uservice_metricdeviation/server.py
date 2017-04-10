#!/usr/bin/env python
"""Retrieve QA metrics and report deviation"""
import json
import os
from apikit import APIFlask as apf
from apikit import BackendError
from flask import jsonify, request
from BitlyOAuth2ProxySession import Session

log = None


def server(run_standalone=False):
    """Create the app and then run it."""
    # Add "/metric_deviation" for mapping behind api.lsst.codes
    squashhost = os.getenv("SQUASH_HOST", "squash.lsst.codes")
    hosturi = "https://" + squashhost
    dataset = os.getenv("SQUASH_DATASET", "cfht")
    app = apf(name="uservice-metricdeviation",
              version="0.0.9",
              repository="https://github.com/sqre-lsst/" +
              "sqre-uservice-metricdeviation",
              description="API wrapper for QA Metric Deviation",
              route=["/", "/metricdeviation"],
              auth={"type": "bitly-proxy",
                    "data": {"username": "",
                             "password": "",
                             "endpoint": hosturi + "/oauth2/start"}})
    global log
    log = app.config["LOGGER"]
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
        params = {"job__ci_dataset": dataset,
                  "metric": metric,
                  "page": "last"}
        log.info("Retrieving metric %s from URL %s" % (metric, url))
        resp = session.get(url, params=params)
        if resp.status_code == 403:
            # Try to reauth
            _reauth(app, inboundauth.username, inboundauth.password)
            session = app.config["SESSION"]
            log.info("Retrying metric %s from URL %s" % (metric, url))
            resp = session.get(url, params)
        if resp.status_code == 200:
            retval = _interpret_response(resp.text, threshold)
            # Get monitor URL
            retval["graph"] = None
            monep = hosturi + "/dashboard/api/metrics/" + metric
            log.info("Retrieving monitor URL from %s" % monep)
            resp = session.get(monep)
            if resp.status_code == 403:
                # Try to reauth
                _reauth(app, inboundauth.username, inboundauth.password)
                session = app.config["SESSION"]
                log.info("Retrying %s" % monep)
                resp = session.get(monep)
            if resp.status_code == 200:
                monurl = _interpret_monitor(resp.text)
                if monurl:
                    retval["graph"] = monurl
            return jsonify(retval)
        else:
            raise BackendError(reason=resp.reason,
                               status_code=resp.status_code,
                               content=resp.text)

    @app.route("/describemetrics")
    @app.route("/metricdeviation/describemetrics")
    def describemetrics():
        """Describe each metric by name"""
        metep = hosturi + "/dashboard/api/metrics"
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
        resp = session.get(metep)
        if resp.status_code == 403:
            # Try to reauth
            _reauth(app, inboundauth.username, inboundauth.password)
            session = app.config["SESSION"]
            log.info("Retrying %s" % metep)
            resp = session.get(metep)
        if resp.status_code == 200:
            retval = _describe_metrics(resp.text)
            return jsonify(retval)
        else:
            raise BackendError(reason=resp.reason,
                               status_code=resp.status_code,
                               content=resp.text)

    @app.errorhandler(BackendError)
    # pylint: disable=unused-variable
    def handle_invalid_usage(error):
        """Custom error handler."""
        errdict = error.to_dict()
        log.error(errdict)
        response = jsonify(errdict)
        response.status_code = error.status_code
        return response
    if run_standalone:
        app.run(host='0.0.0.0', threaded=True)
    # Return app for uwsgi
    return app


def _reauth(app, username, password):
    """Get a session with authentication data"""
    oaep = app.config["AUTH"]["data"]["endpoint"]
    session = Session.Session(oauth2_username=username,
                              oauth2_password=password,
                              authentication_session_url=None,
                              authentication_base_url=oaep)
    session.authenticate()
    global log
    # Update log with username
    log = log.bind(username=username)
    log.info("Reauthenticated with username %s" % username)
    app.config["SESSION"] = session


def _round(num, precision):
    """Round a number to a float with specified precision"""
    fstr = "{0:.%df}" % precision
    return float(fstr.format(num))


def _interpret_response(inbound, threshold):
    """Decide whether there's a reportable deviation"""
    tval = float(threshold)
    try:
        robj = json.loads(inbound)
    except json.decoder.JSONDecodeError as exc:
        raise BackendError(reason="Could not decode JSON result",
                           status_code=500,
                           content=str(exc) + ":\n" + inbound)
    log.debug("Response was:")
    log.debug(json.dumps(robj, sort_keys=True, indent=4))
    results = robj["results"]
    retdict = {"changed": False}
    if len(results) < 2:
        # No previous data to compare to!
        return retdict
    prev = results[-2]
    curr = results[-1]
    unit = ""
    if "unit" in curr:
        unit = curr["unit"]
    pval = prev["value"]
    pval = _round(pval, 3)
    cval = curr["value"]
    cval = _round(cval, 3)
    if pval != cval:
        if pval:
            delta_pct = _round(abs(100.0 * (cval - pval) / pval), 2)
            if delta_pct > tval:
                retdict["changed"] = True
                retdict["current"] = cval
                retdict["previous"] = pval
                retdict["changecount"] = 0
                retdict["delta_pct"] = delta_pct
                retdict["units"] = unit
                ccp = curr["changed_packages"]
                if ccp:
                    retdict["changed_packages"] = ccp
                    retdict["changecount"] = len(ccp)
                # Fetch monitor URL
    return retdict


def _interpret_monitor(inbound):
    """Attempt to get graph URL"""
    url = None
    try:
        robj = json.loads(inbound)
    except json.decoder.JSONDecodeError as exc:
        raise BackendError(reason="Could not decode JSON result",
                           status_code=500,
                           content=str(exc) + ":\n" + inbound)
    log.debug("Response was:")
    log.debug(json.dumps(robj, sort_keys=True, indent=4))
    if "links" in robj and "monitor-url" in robj["links"]:
        url = robj["links"]["monitor-url"]
    return url


def _describe_metrics(inbound):
    """Build dict of metrics and descriptions"""
    metrics = {}
    try:
        robj = json.loads(inbound)
    except json.decoder.JSONDecodeError as exc:
        raise BackendError(reason="Could not decode JSON result",
                           status_code=500,
                           content=str(exc) + ":\n" + inbound)
    log.debug("Response was:")
    log.debug(json.dumps(robj, sort_keys=True, indent=4))
    if "results" in robj:
        for res in robj["results"]:
            if "metric" in res:
                desc = ""
                if "description" in res:
                    desc = res["description"]
                metrics[res["metric"]] = desc
    return metrics


def standalone():
    """Entry point for running as its own executable."""
    server(run_standalone=True)


if __name__ == "__main__":
    standalone()
