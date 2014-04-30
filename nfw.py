#!/usr/bin/env python

from __future__ import division

import math

import numpy as np
from numpy.lib import scimath as sm
import scipy.constants
import scipy.optimize as opt

import astropy.cosmology
from astropy import units as u


def arcsec(z):
    """Compute the inverse sec of the complex number z."""
    val1 = 1j / z
    val2 = sm.sqrt(1 - 1./z**2)
    val = 1.j * np.log(val2 + val1)
    return 0.5 * np.pi + val


def unit_checker(x, unit):
    """Check that x has units u. Convert to appropriate units if not.

    Arguments:
    - `x`: array_like
    - `u`: astro.units unit
    """
    if not isinstance(x, u.Quantity):
        return x * unit
    return x.to(unit)


class NFW(object):
    """Compute properties of an NFW halo.

    Required inputs are

    size - radius or mass of the halo in Mpc or M_sun
    c - concentration (value|"duffy|dolag")
    z - halo redshift

    optional input

    size_type - "(radius|mass)" specifies whether the halo size is given as
                radius or mass
    overdensity - the factor above the critical/mean density of the Universe
                  at which mass/radius are computed. Default 200
    overdensity_type = "(critical|mean)"
    cosmology - object, use the current astropy.cosmology if None, otherwise
                an astropy.cosmology object
    """

    def __init__(self, size, c, z, size_type="mass",
                 overdensity=200, overdensity_type="critical",
                 cosmology=None):

        if overdensity_type not in ['critical', 'mean']:
            raise ValueError("overdensity_type must be one of 'mean', "
                             "'background'")
        self._overdensity_type = overdensity_type

        if size_type not in ['mass', 'radius']:
            raise ValueError("size_type must be one of 'mass', 'radius'")
        self._size_type = size_type

        self._c = float(c)
        self._z = float(z)
        self._overdensity = overdensity
        if cosmology is not None:
            self._cosmology = cosmology
            self._var_cosmology = False
        else:
            self._cosmology = astropy.cosmology.get_current()
            self._var_cosmology = True

        if size_type == "mass":
            self._size = unit_checker(size, u.solMass)
        else:
            self._size = unit_checker(size, u.Mpc)

        self._rho_c = None
        self._r_s = None
        self._r_Delta = None
        self._update_new_cosmology()

        return

    def _update_required(self):
        """
        Check whether the instance needs updating due to a new cosmology
        """
        if not self._var_cosmology:
            return False
        if self._cosmology == astropy.cosmology.get_current():
            return False
        return True

    def _update_new_cosmology(self):
        if self._var_cosmology:
            self._cosmology = astropy.cosmology.get_current()
        self._update_rho_c()
        self._update_r_Delta()
        self._update_r_s()
        return

    def _update_rho_c(self):
        self._rho_c = self._cosmology.critical_density(self.z)
        self._rho_c = self._rho_c.to(u.solMass / u.Mpc**3)
        return

    def _update_r_Delta(self):
        if self._size_type == "mass":
            if self._overdensity_type == 'critical':
                rho = self._rho_c
            else:
                rho = self._rho_c * self._cosmology.Om(self.z)

            self._r_Delta = (3 * self._size / (4*np.pi)
                             * 1 / (self._overdensity*rho))**(1/3)
        else:
            self._r_Delta = self._size
        return

    def _update_r_s(self):
        self._r_s = self.r_Delta / self.c
        return

    @property
    def var_cosmology(self):
        """True if the cosmology always is the current astropy.cosmology
        one. False if the cosmology is held fixed at the one used at
        instantiation."""
        return self._var_cosmology

    @property
    def overdensity_type(self):
        return self._overdensity_type

    @property
    def overdensity(self):
        return self._overdensity

    @property
    def cosmology(self):
        """The cosmology used by this halo."""
        if self._update_required():
            self._update_new_cosmology()
        return self._cosmology

    @property
    def rho_c(self):
        """Critical density at halo redshift
        """
        if self._update_required():
            self._update_new_cosmology()
        return self._rho_c

    @property
    def r_Delta(self):
        """Halo radius at initialization overdensity
        """
        if self._update_required():
            self._update_new_cosmology()
        return self._r_Delta

    @property
    def r_s(self):
        """Scale radius
        """
        if self._update_required():
            self._update_new_cosmology()
        return self._r_s

    @property
    def c(self):
        """Halo concentration"""
        return self._c

    @property
    def z(self):
        """Halo redshift"""
        return self._z

    @property
    def delta_c(self):
        """Characteristic overdensity
        """
        return self._overdensity/3 * self.c**3 / (np.log(1 + self.c)
                                                  - self.c/(1. + self.c))

    def concentration(self, overdensity=None, overdensity_type=None):
        """Return the concencration parameter at overdensity and
        overdensity_type. If both are None, return the concentration at the
        overdensity and type specified at instantiation."""
        print overdensity
        if overdensity is None and overdensity_type is None:
            return self.c
        overdensity = overdensity
        overdensity_type = overdensity_type
        return self.radius_Delta(overdensity, overdensity_type) / self.r_s

    def __str__(self):
        prop_str = "NFW halo with concentration %.2g at redshift %.2f:\n\n" \
                   % (self.c, self.z,)
        for delta in (200, 500, 2500):
            prop_str += "M_%d = %.2e M_sun\tr_%d = %.2g Mpc\n" % \
                        (delta, self.mass_Delta(delta).value, delta,
                         self.radius_Delta(delta).value)
        return prop_str

    def __repr__(self):
        return self.__str__()

    def _mean_density_zero(self, r, Delta, overdensity_type=None):
        if overdensity_type is None:
            overdensity_type = self._overdensity_type
        if overdensity_type == 'critical':
            rho = self.rho_c
        else:
            rho = self.rho_c * self.cosmology.Om(self.z)
        return (self.mean_density(r) - Delta*rho).value

    def radius_Delta(self, Delta, overdensity_type=None):
        """Find the radius at which the mean density is Delta times the
        critical density. Returns radius in Mpc."""
        if overdensity_type is None:
            overdensity_type = self._overdensity_type
        x0 = opt.brentq(self._mean_density_zero, 1e-6, 10,
                        args=(Delta, overdensity_type))
        return x0 * u.Mpc

    def mass_Delta(self, Delta, overdensity_type=None):
        """Find the mass inside a radius inside which the mean density
        is Delta times the critical density. Returns mass in M_sun."""
        if overdensity_type is None:
            overdensity_type = self._overdensity_type
        r = self.radius_Delta(Delta, overdensity_type)
        return self.mass(r)

    def density(self, r):
        """Compute the density rho of an NFW halo at radius r (in Mpc)
        from the center of the halo. Returns M_sun/Mpc^3."""
        r = unit_checker(r, u.Mpc)
        x = r / self.r_s
        return self.rho_c * self.delta_c/(x * (1+x)**2)

    def mean_density(self, r):
        """Compute the mean density inside a radius r (in Mpc). Returns
        M_sun/Mpc^3.
        """
        r = unit_checker(r, u.Mpc)
        x = r / self.r_s
        return 3 * (1/x)**3 * self.delta_c * self.rho_c \
            * (np.log((1 + x)) - x/(1 + x))

    def mass(self, r):
        """Compute the mass of an NFW halo inside radius r (in Mpc)
        from the center of the halo. Returns mass in M_sun."""
        r = unit_checker(r, u.Mpc)
        x = r / self.r_s
        return 4 * np.pi * self.delta_c * self.rho_c * self.r_s**3 \
            * (np.log((1 + x)) - x/(1 + x))

    def projected_mass(self, r):
        """Compute the projected mass of the NFW profile inside a cylinder of
        radius r.

        Parameters:
        ===========
        r: float or astropy.Quantity, radius of the cylinder

        Returns:
        ========
        m_proj: astropy.Quantity, projected mass in the cylinder
        """
        r = unit_checker(r, u.Mpc)
        x = (r / self.r_s).value
        fc = np.log(1 + self.c) - self.c / (1 + self.c)
        f = (arcsec(x) / sm.sqrt(x**2 - 1)).real
        m_proj = self.mass_Delta(self._overdensity) / fc * (np.log(x / 2) + f)
        return m_proj

    def sigma(self, r):
        """Compute the surface mass density of the halo at distance r
        (in Mpc) from the halo center."""
        r = unit_checker(r, u.Mpc)
        x = r / self.r_s
        val1 = 1 / (x**2 - 1)
        val2 = (arcsec(x) / (sm.sqrt(x**2 - 1))**3).real
        return 2 * self.r_s * self.rho_c * self.delta_c * (val1-val2)

    def delta_sigma(self, r):
        """Compute the Delta surface mass density of the halo at
        radius r (in Mpc) from the halo center."""
        r = unit_checker(r, u.Mpc)
        x = r / self.r_s
        fac = 2 * self.r_s * self.rho_c * self.delta_c
        val1 = 1 / (1 - x**2)
        num = ((3 * x**2) - 2) * arcsec(x)
        div = x**2 * (sm.sqrt(x**2 - 1))**3
        val2 = (num / div).real
        val3 = 2 * np.log(x / 2) / x**2
        return fac * (val1+val2+val3)
