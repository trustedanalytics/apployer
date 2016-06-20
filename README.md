[![Dependency Status](https://www.versioneye.com/user/projects/57234ee8ba37ce00350af319/badge.svg?style=flat)](https://www.versioneye.com/user/projects/57234ee8ba37ce00350af319)

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
* Install prerequisites:
    * Ubuntu Desktop: 
        + `$ sudo apt-get install python-dev libffi-dev libssl-dev`
    * Ubuntu Server: 
        + `$ sudo apt-get install python-dev libffi-dev libssl-dev build-essential`
    * CentOS:
        + `$ sudo yum install python-devel libffi-devel openssl-devel`
        + `$ sudo yum groupinstall 'Development Tools'`
* Install setup-tools: `$ curl 'https://bootstrap.pypa.io/ez_setup.py' -o - | sudo -E python`
* Install apployer in your system Python: `$ sudo python setup.py install` or inside a virtualenv: `$ python setup.py install`

Be sure that you have configured /etc/hosts properly. For this purpose run command hostname. As a result of this operation you will see hostname of your machine. Now open /etc/hosts file and find there one line: 127.0.0.1 <your_hostname>. If you cannot find it, you should add it there.

## Local development in PyCharm
* Install Tox: `$ sudo pip install --upgrade tox`
* Run tests: `$ tox`
* Open apployer repository in PyCharm
* Go to File->Settings...->Project:apployer->Project Interpreter->Add Local
* Set python interpreter to cloned_apployer_repository_dir/.tox/py27/bin/python and click OK.
* Next go to Run->Debug and add new Python configuration
* Set parameters to given values and click OK:
    * Script: cloned_apployer_repository_dir/.tox/py27/bin/apployer
    * Script parameters: apployer_command (e.g. -v fetch apps)
    * Python Interpreter: previously create interpreter from .tox directory
    * Working directory: cloned_apployer_repository_dir
* Prepare necessary files according to [Usage](#usage-deployment) section and run debug in PyCharm IDE.
    

## Adding new element to TAP deployment
To add applications, services, brokers or overwriting their configuration, modify `appstack.yml` file in the following way:

* New service offering on TAP -> add offering name to `broker_config::services` list
* New service-instances on TAP -> add instance name to `broker_config::service_instances` list
* New user-provided-service-instances on TAP -> add new element to `user_provided_services` list
* New Application on TAP -> add application element along with it's `app_properties` to `apps::your_app` list
* New Broker on TAP -> add `broker_config` to `apps::your_broker_app::app_properties` list

To make your app accessible as service-offering, add new app to section `# APPS IN APPLICATION BROKER` in `appstack.yml`.
(more information about application-broker available at https://github.com/trustedanalytics/application-broker)

At the moment, documentation of the fields that can be used is in `apployer/appstack.py` file,
in classes: AppConfig, BrokerConfig, UserProvidedService, ServiceInstance, PushOptions.

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
