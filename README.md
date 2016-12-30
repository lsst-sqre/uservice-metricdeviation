[![Build Status](https://travis-ci.org/lsst-sqre/sqre-apikit.svg?branch=master)](https://travis-ci.org/lsst-sqre/sqre-apikit)

# sqre-uservice-metricdeviation

LSST DM SQuaRE microservice wrapper for QA metrics; more
generally, a minimal viable example for how to use the `apikit`
interfaces to create a SQuaRE-compliant microservice.

## Usage

Create a Flask app (preferably using :class:`apikit.APIFlask`).  If you
have used `APIFlask`, it will already have a metadata route (but if you
are using Kubernetes ingress, you will want to specify the additional
route behind api.lsst.codes (or wherever) as one of the arguments to
route.

Hook your app up with whatever authenticator to Github it needs (if
any), and whatever secrets the authenticator requires.

If you're planning on hosting in a container via Kubernetes, create a
service and a deployment for it (look in `kubernetes`), and then if you
are standing up the front end too, set up an ingress with TLS
certificate and key.  If one already exists (e.g. `api.lsst.codes`) you
just need to add a path to the existing ingress.
