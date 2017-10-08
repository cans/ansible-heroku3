****************
Ansible Heroku 3
****************


Manage your Heroku applications with ansible:

- Create and Delete App;
- Configure them;
- Start, Scale and Stop them;

Very early work in progress, the documentation very scarce. Look at the
``heroku.yml`` playbook for usage examples.


Running the sample playbook
===========================

You will also need a file named `credentials.yml` under `vars/` that contains a
variable ``heroku_api_key`` and is set with you very own Heroku API Key
(go to https://dashboard.heroku.com/account to get your key), as well as an
``heroku_application_name`` variable with an application name of your own,
and another ``heroku_existing_application_name`` to try the playbook plays
that assume a pre-existing app.


Dependencies
============

This module relies on the `herok3.py <http://github.com/martyzz1/heroku3.py>`_
Python module.


TODO
====

- Implement the ``apps`` command;
- Retrieve regions dynamically (heroku3.py seems to lack support;
- Add caching to avoid excessive API calls;
- Instead of the ``create`` / ``delete`` commands, implement an ``app``
  command that has a ``state`` argument: ``"present"`` meaning create if
  not exists, ``"absent"`` delete if exists, code is here, it's just a matter
  of reworking the interface;
- Add ability to restart an app (command ``app`` with ``state`` value set
  to ``restarted``;
- config command: ``uppercase`` ``yes``/``no`` option is ambiguous, move
  for ``case`` ``upper``/``lower``/``asis`` with that last one as default;
- Understand how one is supposed to ship extra modules for Ansible, in a
  sensible and user friendly manner;
- Do we need this: manage builds, releases, etc. ?


Known limitations
=================

Heroku's documentation suggests that one can have mixed type of Dynos for a single
application. Never used that and not clear to me how to implement that with
the API (https://devcenter.heroku.com/articles/dyno-types#default-scaling-limits)


Credits
=======

Credits should go first to _martizzz_ for his work on the python heroku3
module without which this Ansible module would not function.

There is a `similar module <https://github.com/s0enke/ansible-heroku>`_
available, but the project has not seen much work and uses a deprecated
Python wrapper for Heroku's REST API.

