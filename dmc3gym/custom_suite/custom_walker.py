# Copyright 2017 The dm_control Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or  implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================

"""Planar Walker Domain."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import collections

from dm_control import mujoco
from dmc3gym.custom_suite import control
from dm_control.suite import base
from dm_control.suite import common
from dm_control.suite.utils import randomizers
from dm_control.utils import containers
from dm_control.utils import rewards
from lxml import etree

_DEFAULT_TIME_LIMIT = 25
_CONTROL_TIMESTEP = .025

# Minimal height of torso over foot above which stand reward is 1.
_STAND_HEIGHT = 1.2

# Horizontal speeds (meters/second) above which move reward is 1.
_WALK_SPEED = 1
_RUN_SPEED = 8


SUITE = containers.TaggedTasks()


def get_model_and_assets(body_length):
  """Returns a tuple containing the model XML string and a dict of assets."""
  xml_string = common.read_model('walker.xml')
  mjcf = etree.fromstring(xml_string)
  torso = mjcf.find('./worldbody/body')
  torso.set('pos', "0 0 %g"%(1+body_length))
  torso = mjcf.find('./worldbody/body/geom')
  torso.set('size', "0.07 %g"%body_length)
  #right = mjcf.find('./worldbody/body/body/body/')
  #right.set('pos', "0 0 %g"%leg_length)
  #right = right.getnext()
  #right.set('size', "0.04 %g"%leg_length)
  #right = right.getnext()
  #right.set('pos', "0.06 0 -%g"%leg_length)
  #left = mjcf.find('./worldbody/body/body').getnext()
  #left = left.getchildren()[2].getchildren()[0]
  #left.set('pos', "0 0 %g"%leg_length)
  #left =left.getnext()
  #left.set('size', "0.04 %g"%leg_length)
  #left = left.getnext()
  #left.set('pos', "0.06 0 -%g"%leg_length)
  return etree.tostring(mjcf, pretty_print=True), common.ASSETS
  #return common.read_model('walker.xml'), common.ASSETS


@SUITE.add('benchmarking')
def stand(time_limit=_DEFAULT_TIME_LIMIT, random=None, params=None, environment_kwargs=None):
  """Returns the Stand task."""
  physics = []
  for leg_length in params:
    physic = Physics.from_xml_string(*get_model_and_assets(leg_length))
    physics.append(physic)
  task = PlanarWalker(move_speed=0, random=random)
  environment_kwargs = environment_kwargs or {}
  return control.Environment(
      physics, task, time_limit=time_limit, control_timestep=_CONTROL_TIMESTEP,
      **environment_kwargs)


@SUITE.add('benchmarking')
def walk(time_limit=_DEFAULT_TIME_LIMIT, random=None, params=None, environment_kwargs=None):
  """Returns the Walk task."""
  physics = []
  for leg_length in params:
    physic = Physics.from_xml_string(*get_model_and_assets(leg_length))
    physics.append(physic)
  task = PlanarWalker(move_speed=_WALK_SPEED, random=random)
  environment_kwargs = environment_kwargs or {}
  return control.Environment(
      physics, task, time_limit=time_limit, control_timestep=_CONTROL_TIMESTEP,
      **environment_kwargs)


@SUITE.add('benchmarking')
def run(time_limit=_DEFAULT_TIME_LIMIT, random=None, params=None, environment_kwargs=None):
  """Returns the Run task."""
  physics = []
  for leg_length in params:
    physic = Physics.from_xml_string(*get_model_and_assets(leg_length))
    physics.append(physic)
  task = PlanarWalker(move_speed=_RUN_SPEED, random=random)
  environment_kwargs = environment_kwargs or {}
  return control.Environment(
      physics, task, time_limit=time_limit, control_timestep=_CONTROL_TIMESTEP,
      **environment_kwargs)


class Physics(mujoco.Physics):
  """Physics simulation with additional features for the Walker domain."""

  def torso_upright(self):
    """Returns projection from z-axes of torso to the z-axes of world."""
    return self.named.data.xmat['torso', 'zz']

  def torso_height(self):
    """Returns the height of the torso."""
    return self.named.data.xpos['torso', 'z']

  def horizontal_velocity(self):
    """Returns the horizontal velocity of the center-of-mass."""
    return self.named.data.sensordata['torso_subtreelinvel'][0]

  def orientations(self):
    """Returns planar orientations of all bodies."""
    return self.named.data.xmat[1:, ['xx', 'xz']].ravel()


class PlanarWalker(base.Task):
  """A planar walker task."""

  def __init__(self, move_speed, random=None):
    """Initializes an instance of `PlanarWalker`.
    Args:
      move_speed: A float. If this value is zero, reward is given simply for
        standing up. Otherwise this specifies a target horizontal velocity for
        the walking task.
      random: Optional, either a `numpy.random.RandomState` instance, an
        integer seed for creating a new `RandomState`, or None to select a seed
        automatically (default).
    """
    self._move_speed = move_speed
    super(PlanarWalker, self).__init__(random=random)

  def initialize_episode(self, physics):
    """Sets the state of the environment at the start of each episode.
    In 'standing' mode, use initial orientation and small velocities.
    In 'random' mode, randomize joint angles and let fall to the floor.
    Args:
      physics: An instance of `Physics`.
    """
    randomizers.randomize_limited_and_rotational_joints(physics, self.random)
    super(PlanarWalker, self).initialize_episode(physics)

  def get_observation(self, physics):
    """Returns an observation of body orientations, height and velocites."""
    obs = collections.OrderedDict()
    obs['orientations'] = physics.orientations()
    obs['height'] = physics.torso_height()
    obs['velocity'] = physics.velocity()
    return obs

  def get_reward(self, physics):
    """Returns a reward to the agent."""
    standing = rewards.tolerance(physics.torso_height(),
                                 bounds=(_STAND_HEIGHT, float('inf')),
                                 margin=_STAND_HEIGHT/2)
    upright = (1 + physics.torso_upright()) / 2
    stand_reward = (3*standing + upright) / 4
    if self._move_speed == 0:
      return stand_reward
    else:
      move_reward = rewards.tolerance(physics.horizontal_velocity(),
                                      bounds=(self._move_speed, float('inf')),
                                      margin=self._move_speed/2,
                                      value_at_margin=0.5,
                                      sigmoid='linear')
      return stand_reward * (5*move_reward + 1) / 6
