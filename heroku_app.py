#!/usr/bin/env python
# -*- coding: utf-8; -*-
# Copyright © 2017, Nicolas CANIART
# GNU General Public License v2.0 (see COPYING or https://www.gnu.org/licenses/gpl-2.0.txt)  # NOQA
from __future__ import unicode_literals, print_function
import copy
import json
import sys

from ansible.module_utils.basic import AnsibleModule
# WANT_JSON
try:
    from requests.exceptions import HTTPError
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
try:
    import heroku3
    from heroku3.models import BaseResource
    HAS_HEROKU3 = True
except ImportError:
    HAS_HEROKU3 = False


__all__ = ['main']

ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'supported_by': 'community',
                    'status': ['preview'],
                    }

_STATES = ('absent',
           'present',
           'restarted',
           'started',
           'stopped',
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
_HEROKU_STACKS = ('cedar-14',
                  'heroku-16',
                  )
_ARGS_SPEC = {'api_key': {'required': True,
                          'no_log': True,
                          },
              'app': {'required': True,
                      # 'type': 'list',
                      },
              'count': {'required': False,
                        'type': 'int',
                        'default': None,
                        },
              'formation': {'required': False,
                            'type': 'dict',
                            'default': {},
                            },
              'region': {'default': 'us',
                         'choices': _HEROKU_REGIONS,
                         },
              'settings': {'default': {},
                           # 'cause user settings may contain sensitive data
                           'no_log': True,
                           'required': False,
                           'type': 'dict',
                           },
              'size': {'default': None,
                       'choices': _DYNO_SIZES,
                       },
              'stack': {'default': 'cedar',
                        'choices': _HEROKU_STACKS,
                        },
              'state': {'default': 'present',
                        'choices': _STATES,
                        },
              'uppercase': {'required': False,
                            'type': 'bool',
                            'default': False,
                            },
              # Dyno types comes from the Procfile, no possibility to
              # change it.
              # 'workload': {'required': False,
              #              'choices': _DYNO_WORKLOADS,
              #              }
              }


DOCUMENTATION = '''
---
module: heroku
short_description: Manages Heroku applications.
description:
    - Lets you create, delete, scale, ... Heroku applications
version_added: "2.1"
author: "Nicolas CANIART, @cans"
options:
  api_key:
    description: API key to authenticate with Heroku
    required: True
    type: string
  app:
    description: Name of your Heroku application which state change
    required: True
    type: string
  count:
    description:
      - The number of dynos to allocate for the application
      - Use of this option is mutually exclusive with the I(formation) option.
      - When used, this option requires that you also define the I(size) option.
      - Ignored when C(state=stopped) or C(state=absent).
    required: False
  formation:
    default: {{}}
    description:
      - Describes the set of dynos to allocate to your application.
      - Use of this option is mutually exclusive with the I(count) and I(size) option.
      - Ignored when C(state=stopped) or C(state=absent).
      - Note that compared to the I(size) argument you need to strip dashes ('-') from dyno type names.
    required: False
    type: dict
  region:
    description:
      - The datacenter in which host the application.
    choices:
      - {regions}
  settings:
    description:
      - Dictionary of settings to be passed to your application
    required: False
    type: dict
  size:
    description:
      - The type of _dyno_ to use
      - Use of this option is mutually exclusive witht the I(formation) option.
      - When used, this option requires that you also define the I(count) option.
      - Ignored when C(state=stopped) or C(state=absent).
    required: False
  stack:
    default: 'cedar'
    description:
      - The Heroku stack to use U(https://devcenter.heroku.com/articles/stack)
    type: string
  state:
    default: present
    description:
      - The state your application should end-up in.
      - C(absent) means the application should not exists, if it does it is deleted.
      - C(present) means the application should exists, if it does not it is created but has a mere empty shell.
      - C(restarted) means the application should be restarted, if it is running or started if it is C(stopped).
      - C(started) means the application should exist and be running. If it is C(stopped) it is started, if it does not exists the module will fail.
      - C(stopped) means the application should exist and no be running. If it is running it is stopped, if it does not exists the module will fail.
    choices:
      - absent
      - present
      - restarted
      - started
      - stopped
    required: True
  uppercase:
    default: False
    description:
      - Whether to uppercase setting names before sending them to your application
    required: False
    type: bool

requirements:
    - heroku3 Python module
'''.format(states='\n      - '.join(_STATES),  # NOQA
           regions='\n      - '.join(_HEROKU_REGIONS),
           )

EXAMPLES = '''
- name: Create basic app (with homogeneous dyno types)
  heroku_formation:
    apikey: "<your-heroku-api-key>"
    app: "my-app"
    size: "standard-1x"
    count: 3

- name: Create a new application if it does not exist yet
  heroku:
    apikey: "<your-heroku-api-key>"
    app: "my-app"
    state: "present"
    region: "us"
    settings:
      variable: "value"
      path: "/to/some/place"
    uppercase: true
    formation:
      standard1x: 3
      standard2x: 1

- name: Delete an application
  heroku:
    apikey: "<your-heroku-api-key>"
    app: "my-app"
    state: "absent"
'''

RETURN = '''
app:
  description: Name of the application
  type: string
'''

_UNABLE_TO_RETRIEVE_APP_DATA = """
Unabled to retrieve applications data from Heroku
(check your credentials or Heroku's status)."""


def _get_app(module, client, app):
    try:
        apps = client.apps()
    except HTTPError:
        module.fail_json(msg=_UNABLE_TO_RETRIEVE_APP_DATA)

    if app not in apps:
        return None
    else:
        return apps.get(app)


def _check_prerequisites(module,
                         count=None,
                         formation=None,
                         state=None,
                         size=None,
                         **kwargs):
    if state in ('stopped', 'absent'):
        return  # We don't care about 'count', 'formation' and 'size'

    if((not formation and (size is None or count is None)) or
       (formation and size is not None and count is not None)):
        module.fail_json(msg="You must specify either the 'formation' or both"
                         " the 'count' and 'size' options.")

    total_dynos = 0
    safe_dyno_types = {dyno_type.replace('-', ''): dyno_type
                       for dyno_type in _DYNO_SIZES
                       }
    for dyno_type, count in copy.copy(formation).items():
        actual_dyno_type = safe_dyno_types.get(dyno_type)
        if actual_dyno_type is None or count < 0:
            module.fail_json(msg=("Invalid 'formation' value: '{dyno_type}: "
                                  "{count}'"
                                  .format(dyno_type=dyno_type, count=count)))
        else:
            formation[actual_dyno_type] = count
            del formation[dyno_type]
        total_dynos += count

    if not formation:
        formation.update({size: count, })
        total_dynos += count

    if state != 'present' and total_dynos <= 0:
        module.fail_json(msg="You allocated no dynos to your application."
                         " It cannot be running without dynos."
                         " Check you formation or size and count options."
                         )
    # Parameters 'count', 'region', 'size', 'stack', 'state' already checked by
    # the module.
    # Cannot check 'settings' it is user data.


def _configure(module, client, hk_app, settings=None, uppercase=True):
    """Applies settings to the given Heroku application.

    Args:
        module (AnsibleModule): an Ansible module
        client (HerokuClient): an client for Heroku's API
        hk_app (HerokuApp): an Heroku application
        settings (dict[str, Any]): the settings to apply to ``hk_app``
        uppercase (bool): whether to turn settings dict keys to upper
            case before applying settings to ``hk_app``.
    """
    assert hk_app is not None
    import ipdb; ipdb.set_trace()
    results = []
    unknown = object()
    success = True
    try:
        current_settings = hk_app.config()
        current_settings = current_settings.data
    except Exception as e:  # Better handle error
        module.fail_json(msg=("Failed to retrieve `{app}' current configuration."
                              .format(app=hk_app.name)
                              )
                         )

    changed = False
    actual_settings = {}
    for variable, new_value in settings.iteritems():
        if uppercase is True:
            actual_variable = variable.upper()
        else:
            actual_variable = variable

        actual_settings[actual_variable] = str(new_value)
        old_value = current_settings.get(variable, unknown)
        changed |= old_value is unknown or str(new_value) != old_value

    hk_app.update_config(actual_settings)

    return hk_app, {'changed': True,
                    }


def _create(module, client, app=None, region=None, stack=None, **kwargs):
    """Creates a new Heroku application

    Args:
        module (AnsibleModule): the Ansible module instance
        client (heroku3.api.Heroku): the Heroku API client
        app (str): the name of the app to create
        stack (str): the name of the Heroku stack to use
        region (str): the Heroku region in which host the the app

    Returns:
        Application:
    """
    import ipdb; ipdb.set_trace()
    try:
        hk_app = client.create_app(name=app, stack_id_or_name=stack, region_id_or_name=region)
        result = {'changed': True,
                  'heroku_app': _convert_facts(hk_app),
                  }
        return hk_app, result

    except HTTPError as e:
        module.fail_json(msg="Could not create App {app}: {error}"
                         .format(app=app, error=e))


def _absent(module, client, hk_app, **kwargs):
    if hk_app is None:
        module.exit_json(changed=False)

    try:
        hk_app.delete()
    except HTTPError as e:
        module.fail_json(msg="Fail to delete App `{}'.".format(app))

    else:
        module.exit_json(changed=True, msg="App `{}' deleted.".format(app))


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


def _present(module, client, hk_app, **kwargs):
    if hk_app is None:
        hk_app = _create(module, client, **kwargs)
        changed = hk_app is not None
    return hk_app, changed


def _restarted(module, client, hk_app, **kwargs):
    import ipdb; ipdb.set_trace()
    if hk_app is None:
        return _started(module, client, hk_app, **kwargs)

    # Better configure the application before re-starting it
    hk_app, result = _configure(module,
                                client,
                                hk_app,
                                settings=kwargs['settings'],
                                uppercase=kwargs.get('uppercase',
                                                     _ARGS_SPEC['uppercase']['default'],
                                                     ),
                                )

    try:
        hk_app.restart()
    except HTTPError:
        module.fail_json(msg="Failed to restart application '{app}'".format(hk_app.name))
    return hk_app, True


def _scale(module, client, hk_app, formation=None, **kwargs):
    """Given an app, up- or down-scales it.

    If original quantity was 0 and the new one is positive, then this
    starts the application.

    Conversely, if the original quantity is positive and the new one is
    zero, then this stops the application.

    Args:
        module (AnsibleModule): the Ansible module instance
        hk_app (heroku3.models.App): the application to scale
        formation (dict[DynoType, int]): the number of dynos required to be present.

    Returns:
        None: has a side effect on the module
    """
    assert hk_app is not None
    import ipdb; ipdb.set_trace()
    action = None
    try:
        current_formations = hk_app.process_formation()  # Get the "formation"
    except HTTPError:
        module.fail_json(msg=("Could not retrieve '{app}' current formation."
                              .format(app=kwargs['app'])
                              )
                         )

    # Encapsulation violation: implement __len__ on KeyedListResources
    formation_count = len(formation)
    updates = []
    for current_formation in current_formations:
        size = current_formation.size
        type_ = current_formation.type
        if size not in formation:
            quantity = 0  # Remove this type of processes
        else:
            if current_formation.quantity == formation[size]:
                continue  # Nothing to change

            else:
                quantity = formation[size]
        updates.append({'size': size,
                        'quantity': quantity,
                        'type': type_,
                        })

    if updates:
        try:
            formation.batch_formation_update(size=size, quantity=quantity)
            return hk_app, {'changed': True, }

        except HTTPError as e:
            module.fail_json(msg="Could not update app `{app}' formation: "
                             "{error}".format(action=action,
                                              app=hk_app.name,
                                              error=e,
                                              )
                             )
    return hk_app, {'changed': False, }


def _started(module, client, hk_app, formation=None, **kwargs):
    import ipdb ; ipdb.set_trace()
    if hk_app is None:
        hk_app, changed = _present(module, client, hk_app, **kwargs)
    # Better configure the application before starting it
    hk_app, config_changed = _configure(module,
                                        client,
                                        hk_app,
                                        settings=kwargs['settings'],
                                        uppercase=kwargs['uppercase'],
                                        )

    hk_app, scale_changed =  _scale(module,
                                    client,
                                    hk_app,
                                    formation=formation
                                    )




def _stopped(module, client, hk_app, **kwargs):
    print(kwargs, file=sys.stderr)
    if hk_app is None:
        hk_app, present_changed = _present(module, client, hk_app)

    formation_override = dict(izip_longest(_DYNO_SIZES, [0], fillvalue=0))
    hk_app, scale_changed = _scale(module,
                                   client,
                                   hk_app,
                                   formation=formation_override)

    return hk_app, scale_changed or present_changed


def main():
    global _ARGS_SPEC
    _STATE_HANDLERS = {'absent': _absent,
                       'present': _present,
                       'restarted': _restarted,
                       'started': _started,
                       'stopped': _stopped,
                       }

    module = AnsibleModule(argument_spec=_ARGS_SPEC,
                           supports_check_mode=False,
                           )
    if not HAS_HEROKU3:
        module.fail_json(msg="Heroku3 is required for this module. "
                         "Please install heroku3 and try again.")
    if not HAS_REQUESTS:
        module.fail_json(msg="Requests is required for this module. "
                         "Please install requests and try again.")

    params = module.params
    _check_prerequisites(module, **module.params)
    client = heroku3.from_key(params['api_key'])
    del params['api_key']  # So it does not appear in logs.

    command = _STATE_HANDLERS[params['state']]
    hk_app = _get_app(module, client, params['app'])
    hk_app, changed = command(module,
                              client,
                              hk_app,
                              **{k: v
                                 for k, v in module.params.iteritems()
                                 if k not in ['state', ]
                                 }
                              )
    module.exit_json(msg=("Application {app} successfuly {state}."
                          .format(app=hk_app.name, state=params['state'])
                          )
                     )


if __name__ == '__main__':
    main()


# vim: et:sw=4:syntax=python:ts=4:
