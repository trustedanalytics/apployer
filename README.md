# Apployer
Tool for deployment of Cloud Foundry application stack.
Application stack consists of interdependent CF applications, brokers, services and buildpacks.

## Usage (deployment)
Apployer can be run on any machine that has access to a TAP instance (created according to [Infrastructure Deployment](https://github.com/trustedanalytics/platform-wiki/wiki/Getting%20Started%20Guide#platform-and-infrastructure-deployment)). It is, however, recommended to run it on TAP's bastion machine to minimize network latency to Cloud Foundry.

1. Obtain a TAP release package or create it with [platform-parent](https://github.com/trustedanalytics/platform-parent) project.
1. Unpack the release package. Go to Apployer's directory inside the release package: `cd <package>/tools/apployer`.
1. Do steps from "Setup" section below.
1. Fill the fetcher_config.yml file with values corresponding to your TAP instance.
1. If you want to, change values in `VARIABLES FOR MANUAL CHANGE` section of `templates/template_variables.yml`.
1. Run `apployer deploy` command. See `apployer deploy --help` for details and example usage.

## Setup
* Enabling compilation of Python C extensions `$ sudo apt-get install python-dev`
* Install in your system Python: `$ sudo python setup.py install` or inside a virtualenv: `$ python setup.py install`

## Testing
* Install Tox: `$ sudo pip install --upgrade tox`
* Run tests: `$ tox`

## Adding new appstack elements (TODO)
Adding applications, services, brokers or overwriting their configuration - see `appstack.yml`.
There are plenty of examples there.
At the moment, documentation of the fields that can be used is in `apployer/appstack.py`,
in classes: AppConfig, BrokerConfig, UserProvidedService, BrokerConfig, ServiceInstance, PushOptions.

Need new configuration values? edit `templates/template_variables.yml` and scripts in `apployer/fetcher` directory.  

## Troubleshooting
> Cannot create a tunnel to CDH-Manager machine.

Try modyfing configuration of "cdh-manager" in fetcher_config.yml.
It also can have something to do with proxy configuration on the machine from which you're trying to
connect to the CDH-manager.

## Tips &amp; tricks
Creating an expanded appstack dumps the application dependency graph as `app_dependency_graph.xml`.
You can visualise it like this:
```
$ sudo apt-get install graphviz
$ graphml2gv app_dependencies_graph.xml -o app_dependencies_graph.gv
$ dot -Tpdf app_dependencies_graph.gv -o app_dependencies_graph.pdf
```

Enabling tab-completion in Bash: `. autocomplete.sh`

If you want to quickly restart a deployment after a failure of some application's deployment,
you can comment out all the applications before it in filled_appstack.yml.
Bear in mind, that if some of those commented out apps need to be registered in application_broker
it won't happen, because, this occurs after all the apps have been pushed.
