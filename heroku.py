#! /usr/bin/env python
# -*- coding: utf-8; -*-
from __future__ import unicode_literals, print_function
import json
import sys

from ansible.module_utils.basic import AnsibleModule
# WANT_JSON
import heroku3
from heroku3.models import BaseResource
from requests.exceptions import HTTPError


__all__ = ['main']

DOCUMENTATION = '''
---
module: heroku
short_description: Manages Heroku applications
description:
  - Let's you create and delete Heroku applications
  - Let's you query and or update application's configuration
version_added: "2.1"
author: "Nicolas CANIART, @cans"
requirements:
    - heroku3 Python module
# ... snip ...
'''

EXAMPLES = '''
- name: Create a new application
  heroku:
    apikey: "<your-heroku-api-key>"
    app: "my-app"
    command: create
    region: "us"

- name: 
  heroku:
    apikey: "<your-heroku-api-key>"
    app: "my-app"
    command: config
    settings:
      variable: "value" 
      path: "/to/some/place"
    uppercase: true

- name: Delete an application
  heroku:
    apikey: "<your-heroku-api-key>"
    app: "my-app"
    command: delete
'''

RETURN = '''
'''

_COMMANDS = ('apps',
             'config',
             'create',
             'delete',
             'facts',
             'scale',
             'start',
             'stop',
             )
_DYNO_SIZES = ('free',
               'hobby',
               'standard-1x',
               'standard-2x',
               'performance-m',
               'performance-l',
               )
# _DYNO_WORKLOADS = ('web',
#                    'worker',
#                    )
_HEROKU_REGIONS = ('eu',
                   'frankfurt',
                   'oregon',
                   'tokyo',
                   'us',
                   'virginia',
                   )
_ARGS_SPEC = {'command': {'default': 'facts',
                          'choices': _COMMANDS,
                          }, 
              'app': {'required': False,
                      # 'type': 'list',
                      },
              'apikey': {'required': True,
                         },
              'count': {'required': False,
                        'type': 'int',
                        'default': None,
                        },
              'region': {'default': 'us',
                         'choices': _HEROKU_REGIONS,
                         },
              'size': {'default': None,
                       'choices': _DYNO_SIZES,
                       },
              'stack': {'default': 'cedar',
                        'choices': ('cedar', ),
                        },
              'settings': {'required': False,
                           'type': 'dict',
                           'default': {},
                           },
              'uppercase': {'required': False,
                            'type': 'bool',
                            'default': False,
                            },
              # Dyno types comes from the Procile, no possibility to
              # change it.
              # 'workload': {'required': False,
              #              'choices': _DYNO_WORKLOADS,
              #              }
              }


def _passive(verb):
    if verb[-1] in ['p']:
       return "{}{}ed".format(verb, verb[-1])
    elif verb[-1] in ['t']:
       return '{}ed'.format(verb)
    return '{}d'.format(verb)

 
def _check_app(module, client, app, exists=True):
    apps = client.apps()
    if app not in apps and exists:
        module.fail_json(msg="No such application: `{}'".format(app))
    else:
        return apps.get(app)


def _check_args(module, command, kwargs):
    extras = []
    from StringIO import StringIO
    for arg, value in kwargs.iteritems():
        if value != _ARGS_SPEC[arg].get('default'):
            extras.append(arg)

    if extras:
        module.fail_json(msg=("Unexpected arguments for command '{}': {}"
                              .format(command, ', '.join(extras))
                              )
                         )


def _scale_app(module, hk_app, quantity=None, size=None, **kwargs):
    """Given an app, up- or down-scales it.

    If original quantity was 0 and the new one is positive, then this
    starts the application.

    Conversely, if the original quantity is positive and the new one is
    zero, then this stops the application.

    Args:
        module (AnsibleModule): the Ansible module instance
        hk_app (heroku3.models.App): the application to scale
        quantity (int): the number of dynos required to be present.
        size (int): the type of Dyno to use.

    Returns:
        None:
    """
    action = None
    try:
        formation = hk_app.process_formation()  # Get the "formation"
        # Encapsulation violation: implement __len__ on KeyedListResources
        formation_count = len(formation._items)
        if formation_count > 1:
            module.fail_json(msg="Unhandled use case: application with several process formations")

        if formation_count == 0:
            module.fail_json(msg="App `{app}' has process formation: have you deployed some code on it ?")

        formation = formation[0]

        if formation.quantity < quantity:
            if formation.quantity == 0:
                action = 'start'
            else:
                action = 'up-scale'
        elif formation.quantity > quantity:
            if quantity == 0:
                action = 'stop'
            else:
                action = 'down-scale'

        if formation and (formation.quantity != quantity or size != formation.size):
            formation.update(size=size, quantity=quantity)

    except HTTPError as e:
        module.fail_json(msg="Could not {action} app `{app}': {error}"
                         .format(action=action, app=hk_app.name, error=e))
    else:
        if action is not None:
            msg = ('App {app} successfully {action}.'
                   .format(app=hk_app.name, action=_passive(action))
                   )
        else:
            msg = "App `{app}' left unchanged.".format(app=hk_app.name)
        module.exit_json(changed=action is not None, msg=msg)


def _apps(module, client, app=None, **kwargs):
    pass


def _app(module, client, app=None, state=None, **kwargs):
    action = {'absent': _delete,
              'present': _create,
              'restarted': _restart,
              'started': _start,
              'stopped': _stop,
              }
    pass  # TODO


def _config(module, client, app=None, settings=None, uppercase=True, **kwargs):
    """
    """
    _check_args(module, 'config', kwargs)
    hk_app = _check_app(module, client, app)
    results = []
    unknown = object()
    success = True
    try:
        current_settings = hk_app.config()
        current_settings = current_settings.data
    except Exception as e:  # Better handle error
        success = False
        message = ("Failed to update `{}' application's configuration: {}"
                   .format(app, e)
                   )

    if not success:
        module.fail_json(msg=message)
    else:
        changed = False
        actual_settings = {}
        for variable, new_value in settings.iteritems():
             if uppercase is True:
                 actual_variable = variable.upper()
             else:
                 actual_variable = variable

             actual_settings[actual_variable] = str(new_value)
             old_value = current_settings.get(variable, unknown)
             changed = old_value is unknown or str(new_value) != old_value

        hk_app.update_config(actual_settings)
        module.exit_json(changed=changed,
                         )


def _create(module, client, app=None, region=None, stack=None, **kwargs):
    """Creates a new Heroku application

    The presence of the ``stack`` argument is a feeble attempt to make
    this module future-proof: there is only one stack available right
    now.

    Args:
        module (AnsibleModule): the Ansible module instance
        client (heroku3.api.Heroku): the Heroku API client
        app (str): the name of the app to create
        stack (str): the name of the Heroku stack to use
        region (str): the Heroku region in which host the the app

    """
    _check_args(module, 'create', kwargs)
    hk_app = _check_app(module, client, app, exists=False)
    if hk_app is None:
        try:
            hk_app = client.create_app(name=app, stack_id_or_name=stack, region_id_or_name=region)
            module.exit_json(changed=True, heroku_app=_convert_facts(hk_app))
        except HTTPError as e:
            module.fail_json(msg="Could not create App {app}: {error}"
                             .format(app=app, error=e))
    else:
        module.exit_json(changed=False,
                         msg="App `{app}' already exists".format(app=app),
                         heroku_app=_convert_facts(hk_app))


def _convert_facts(fact, exclude=None):
    result = {}
    exclude = exclude or ['app', 'info', 'order_by', ]
    attributes = dir(fact)
    for attr in attributes: 
        if attr.startswith('_') or attr in exclude:
            continue

        value = getattr(fact, attr)
        if callable(value):
            continue
        elif isinstance(value, BaseResource):
            result[attr] = _convert_facts(value, exclude=exclude)
        else:
            result[attr] = value
    return result


def _delete(module, client, app=None, **kwargs):
    _check_args(module, 'delete', kwargs)
    hk_app = _check_app(module, client, app)
    try:
        hk_app.delete()
    except HTTPError as e:
        module.fail_json(msg="Fail to delete App `{}'.".format(app))

    else:
        module.exit_json(changed=True, msg="App `{}' deleted.".format(app))


def _facts(module, client, app=None, **kwargs):
    _check_args(module, 'facts', kwargs)
    hk_app = _check_app(module, client, app)
    facts = _convert_facts(hk_app)
    module.exit_json(changed=True, heroku_app=facts)


def _get_facts(hk_app):
    results = dict() 
    return {'heroku_app': {'name': app,
                           'id': hk_app.id,
                           'raw': data, 
                           },
            }


def _scale(module, client, app=None, size=None, count=None, workload=None, **kwargs):
    _check_args(module, 'scale', kwargs)
    hk_app = _check_app(module, client, app)
    if count < 0:
        module.fail_json(msg="Value of the `count' argument must be positive.")
    _scale_app(module, hk_app, quantity=count, size=size)


def _start(module, client, app=None, size=None, count=None, **kwargs):
    _check_args(module, 'start', kwargs)
    if count <= 0:
        module.fail_json(msg="Value of the `count' argument must be strictly positive.")
    _scale(module, client, app=app, size=size, count=count, **kwargs)


def _stop(module, client, app=None, **kwargs):
    print(kwargs, file=sys.stderr)
    _check_args(module, 'stop', kwargs)
    kwargs.pop('count')
    _scale(module, client, app=app, count=0, **kwargs)



def main():
    global _ARGS_SPEC
    global _COMMANDS
    _HANDLERS = [_apps, _config, _create, _delete, _facts, _scale, _start, _stop, ]
    _COMMAND_HANDLERS = dict(zip(_COMMANDS, _HANDLERS))

    module = AnsibleModule(argument_spec=_ARGS_SPEC,
                           supports_check_mode=False,
                           )
    p = module.params
    client = heroku3.from_key(p['apikey'])
    del p['apikey']  # So it does not appear in logs.

    command = _COMMAND_HANDLERS[p['command']]
    results = command(module, client, **{k: v for k, v in module.params.iteritems() if k != 'command'})


if __name__ == '__main__':
    main()


# vim: syntax=python:sws=4:sw=4:et:
