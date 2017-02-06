[![Build Status](https://travis-ci.org/lsst-sqre/sqre-apikit.svg?branch=master)](https://travis-ci.org/lsst-sqre/sqre-apikit)

# sqre-uservice-metricdeviation

LSST DM SQuaRE microservice wrapper for QA metrics.

## Usage

`GET /metricdeviation/<metric>/<threshold>`

* Metric is one of the metrics we know about (AM1, AM2, PA1).  Threshold
  is a floating point number indicating the percentage change since the
  last run we want to be notified about.

`GET /metricdeviation/<metric>`

* Same as above with a threshold of 0.0.

## Return

You will get a JSON object back, with at least the field "changed".
That will be "true" or "false".  If changed is true, the following
fields will be set.

* "current"          : current metric value
* "previous"         : previous metric value
* "delta_pct"        : absolute value of change as percentage of value
* "units"            : units of metric
* "changecount"      : number of packages changed between current and
  previous run
* "changed_packages" : list of packages changed between current and
  previous run
