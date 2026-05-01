# Copyright 2014 (C) Adam Greig
#
# This file is part of Tawhiri.
#
# Tawhiri is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Tawhiri is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Tawhiri.  If not, see <http://www.gnu.org/licenses/>.

"""
Provide all the balloon models, termination conditions and
functions to combine models and termination conditions.
"""

import calendar
import math

from . import interpolate


_PI_180 = math.pi / 180.0
_180_PI = 180.0 / math.pi


## Up/Down Models #############################################################


def make_constant_ascent(ascent_rate):
    """Return a constant-ascent model at `ascent_rate` (m/s)"""
    def constant_ascent(t, lat, lng, alt):
        return 0.0, 0.0, ascent_rate
    return constant_ascent

#岩谷の論文再現コード
def make_varying_ascent(initial_ascent_rate, surface_temp_k, dataset, warningcounts):
    """
    気温の逆数に比例して上昇速度が変化するモデル (岩谷技研の論文に基づく)
    v = v_i * (T_s / T)
    """
    # 拡張したインターポレータを取得
    get_wind_and_temp = interpolate.make_interpolator(dataset, warningcounts)
    dataset_epoch = calendar.timegm(dataset.ds_time.timetuple())

    def varying_ascent(t, lat, lng, alt):
        # (u, v, temp) を取得
        u, v, temp = get_wind_and_temp((t - dataset_epoch) / 3600.0, lat, lng, alt)
        
        # 論文の式(8)を適用: 速度 = 初期速度 * (地表気温 / 現在気温)
        # 気温が下がる（高度が上がる）ほど、v_z は大きくなる
        v_z = initial_ascent_rate * (surface_temp_k / temp)
        
        # 水平方向の移動(dlat, dlng)はここでは計算せず、垂直方向(dalt)のみ返す
        return 0.0, 0.0, v_z

    return varying_ascent


def make_drag_descent(sea_level_descent_rate):
    """Return a descent-under-parachute model with sea level descent
       `sea_level_descent_rate` (m/s). Descent rate at altitude is determined
       using an altitude model courtesy of NASA:
       http://www.grc.nasa.gov/WWW/K-12/airplane/atmosmet.html

       For a given altitude the air density is computed, a drag coefficient is
       estimated from the sea level descent rate, and the resulting terminal
       velocity is computed by the returned model function.
    """
    def density(alt):
        temp = pressure = 0.0
        if alt > 25000:
            temp = -131.21 + 0.00299 * alt
            pressure = 2.488 * ((temp + 273.1)/(216.6)) ** (-11.388)
        elif 11000 < alt <= 25000:
            temp = -56.46
            pressure = 22.65 * math.exp(1.73 - 0.000157 * alt)
        else:
            temp = 15.04 - 0.00649 * alt
            pressure = 101.29 * ((temp + 273.1)/288.08) ** (5.256)
        return pressure / (0.2869*(temp + 273.1))

    drag_coefficient = sea_level_descent_rate * 1.1045

    def drag_descent(t, lat, lng, alt):
        return 0.0, 0.0, -drag_coefficient/math.sqrt(density(alt))
    return drag_descent


## Sideways Models ############################################################


def make_wind_velocity(dataset, warningcounts):
    """Return a wind-velocity model, which gives lateral movement at
       the wind velocity for the current time, latitude, longitude and
       altitude. The `dataset` argument is the wind dataset in use.
    """
    get_wind = interpolate.make_interpolator(dataset, warningcounts)
    dataset_epoch = calendar.timegm(dataset.ds_time.timetuple())
    def wind_velocity(t, lat, lng, alt):
        t -= dataset_epoch
# tempも返ってくるので3つで受け取る (横移動にtempは不要なので捨てる)
        u, v, _temp = get_wind(t / 3600.0, lat, lng, alt)
        R = 6371009 + alt
        dlat = _180_PI * v / R
        dlng = _180_PI * u / (R * math.cos(lat * _PI_180))
        return dlat, dlng, 0.0
    return wind_velocity


def make_reverse_wind_velocity(dataset, warningcounts):
    """Return a reverse wind-velocity model, which gives reverse lateral movement at
       the wind velocity for the current time, latitude, longitude and
       altitude. The `dataset` argument is the wind dataset in use.
       This allows working estimation of a radiosonde's launch site.
    """
    get_wind = interpolate.make_interpolator(dataset, warningcounts)
    dataset_epoch = calendar.timegm(dataset.ds_time.timetuple())

    def wind_velocity(t, lat, lng, alt):
        t -= dataset_epoch
        # tempも返ってくるので3つで受け取る (横移動にtempは不要なので捨てる)
        u, v, _temp = get_wind(t / 3600.0, lat, lng, alt)
        # Reverse the sign of the u & v wind components
        u = -1 * u
        v = -1 * v
        R = 6371009 + alt
        dlat = _180_PI * v / R
        dlng = _180_PI * u / (R * math.cos(lat * _PI_180))
        return dlat, dlng, 0.0
    return wind_velocity


## Termination Criteria #######################################################


def make_burst_termination(burst_altitude):
    """Return a burst-termination criteria, which terminates integration
       when the altitude reaches `burst_altitude`.
    """
    def burst_termination(t, lat, lng, alt):
        if alt >= burst_altitude:
            return True
    return burst_termination


def sea_level_termination(t, lat, lng, alt):
    """A termination criteria which terminates integration when
       the altitude is less than (or equal to) zero.

       Note that this is not a model factory.
    """
    if alt <= 0:
        return True

def make_elevation_data_termination(dataset=None):
    """A termination criteria which terminates integration when the
       altitude goes below ground level, using the elevation data
       in `dataset` (which should be a ruaumoko.Dataset).
    """
    def tc(t, lat, lng, alt):
        return (dataset.get(lat, lng) > alt) or (alt <= 0)
    return tc

def make_time_termination(max_time):
    """A time based termination criteria, which terminates integration when
       the current time is greater than `max_time` (a UNIX timestamp).
    """
    def time_termination(t, lat, lng, alt):
        if t > max_time:
            return True
    return time_termination

def make_dummy_termination():
    """A dummy termination criteria, which immediately terminates """
    def dum(t, lat, lng, alt):
        return True
    return dum


## Model Combinations #########################################################


def make_linear_model(models):
    """Return a model that returns the sum of all the models in `models`.
    """
    def linear_model(t, lat, lng, alt):
        dlat, dlng, dalt = 0.0, 0.0, 0.0
        for model in models:
            d = model(t, lat, lng, alt)
            dlat, dlng, dalt = dlat + d[0], dlng + d[1], dalt + d[2]
        return dlat, dlng, dalt
    return linear_model


def make_any_terminator(terminators):
    """Return a terminator that terminates when any of `terminators` would
       terminate.
    """
    def terminator(t, lat, lng, alt):
        return any(term(t, lat, lng, alt) for term in terminators)
    return terminator


## Pre-Defined Profiles #######################################################


def standard_profile(ascent_rate, burst_altitude, descent_rate,
                     wind_dataset, elevation_dataset, warningcounts):
    """Make a model chain for the standard high altitude balloon situation of
       ascent at a constant rate followed by burst and subsequent descent
       at terminal velocity under parachute with a predetermined sea level
       descent rate.

       Requires the balloon `ascent_rate`, `burst_altitude` and `descent_rate`,
       and additionally requires the dataset to use for wind velocities.

       Returns a tuple of (model, terminator) pairs.
    """

    model_up = make_linear_model([make_constant_ascent(ascent_rate),
                                  make_wind_velocity(wind_dataset, warningcounts)])
    term_up = make_burst_termination(burst_altitude)

    model_down = make_linear_model([make_drag_descent(descent_rate),
                                    make_wind_velocity(wind_dataset, warningcounts)])
    term_down = make_elevation_data_termination(elevation_dataset)

    return ((model_up, term_up), (model_down, term_down))


def float_profile(ascent_rate, float_altitude, stop_time, dataset, warningcounts):
    """Make a model chain for the typical floating balloon situation of ascent
       at constant altitude to a float altitude which persists for some
       amount of time before stopping. Descent is in general not modelled.
    """

    model_up = make_linear_model([make_constant_ascent(ascent_rate),
                                  make_wind_velocity(dataset, warningcounts)])
    term_up = make_burst_termination(float_altitude)
    model_float = make_wind_velocity(dataset, warningcounts)
    term_float = make_time_termination(stop_time)

    return ((model_up, term_up), (model_float, term_float))


def reverse_profile(ascent_rate, wind_dataset, elevation_dataset, warningcounts):
    """Make a model chain used to estimate a balloon's launch site location, based on
       the current position, and a known ascent rate. This model only works for a balloon
       on ascent.

       Requires the balloon `ascent_rate`,
       and additionally requires the dataset to use for wind velocities.

       Returns a tuple of (model, terminator) pairs.
    """

    model_up = make_linear_model([make_constant_ascent(ascent_rate),
                                  make_wind_velocity(wind_dataset, warningcounts)])

    term_up = make_dummy_termination()

    model_down = make_linear_model([make_constant_ascent(abs(ascent_rate)),
                                    make_wind_velocity(wind_dataset, warningcounts)])
    term_down = make_elevation_data_termination(elevation_dataset)

    return ((model_up, term_up), (model_down, term_down))

def iwaya_profile(initial_ascent_rate, surface_temp_k, burst_altitude, descent_rate,
                  wind_dataset, elevation_dataset, warningcounts):
    """
    岩谷技研モデルを使用したフルシミュレーションプロファイル
    standard_profileの「上昇」部分を気温依存モデルに差し替えたもの。
    """
    # 1. 上昇フェーズ (気温依存モデル + 横風モデル)
    model_up = make_linear_model([
        make_varying_ascent(initial_ascent_rate, surface_temp_k, wind_dataset, warningcounts),
        make_wind_velocity(wind_dataset, warningcounts)
    ])
    term_up = make_burst_termination(burst_altitude)

    # 2. 下降フェーズ (パラシュート降下モデル + 横風モデル)
    model_down = make_linear_model([
        make_drag_descent(descent_rate),
        make_wind_velocity(wind_dataset, warningcounts)
    ])
    term_down = make_elevation_data_termination(elevation_dataset)

    # ソルバーが読めるように (モデル, 終了条件) のタプルにして返す
    return ((model_up, term_up), (model_down, term_down))