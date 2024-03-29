"""
@author Andrea Passarelli
@date 23. February 2016
@brief Synchrotron radiation damping effect in transverse and longitudinal planes.
@copyright CERN
"""



import numpy as np
from scipy.constants import c


class SynchrotronRadiationTransverse(object):
    def __init__(self, eq_emit_x, eq_emit_y, damping_time_x_turns, damping_time_y_turns, beta_x, beta_y):
        '''
        We are assuming no alpha, etc.
        '''
        #TRANSVERSE
        self.tau_x  = damping_time_x_turns #Damping time [turns]
        self.tau_y  = damping_time_y_turns #Damping time [turns]
        self.epsn_x = eq_emit_x   #Equilibrium emittance [m.rad]
        self.epsn_y = eq_emit_y   #Equilibrium emittance [m.rad]
        self.beta_x = beta_x      #Beta average
        self.beta_y = beta_y      #Beta average
        
    def track(self, bunch):
        
        #TRANSVERSE
        sigma_xp = np.sqrt(self.epsn_x/self.beta_x/bunch.beta/bunch.gamma)
        sigma_yp = np.sqrt(self.epsn_y/self.beta_y/bunch.beta/bunch.gamma)
        bunch.xp -= 2*bunch.xp/self.tau_x
        bunch.xp += 2*sigma_xp*np.sqrt(1/self.tau_x)*np.random.normal(size=len(bunch.xp))
        bunch.yp -= 2*bunch.yp/self.tau_y
        bunch.yp += 2*sigma_yp*np.sqrt(1/self.tau_y)*np.random.normal(size=len(bunch.yp))
        
class SynchrotronRadiationLongitudinal(object):
    def __init__(self, eq_sig_dp, damping_time_z_turns, E_loss_eV, D_x = None, D_y = None):
        '''
        We are assuming no alpha, etc.
        '''
        
        #LONGITUDINAL
        self.tau_z  = damping_time_z_turns    #Damping time [turns]
        self.E_loss_eV = E_loss_eV         #Energy loss [eV]
        self.sigma_dpp0  = eq_sig_dp #Equilibrium momentum spread 
        
        if D_x == None or D_y == None:
            self.track = self.track_without_dispersion
        else:
            self.D_x = D_x
            self.D_y = D_y
            self.track = self.track_with_dispersion
    
    def track_with_dispersion(self,bunch):
        ''' Subtract the dispersion before computing a new dp, then add
        the dispersion using the new dp.
        '''
        #LONGITUDINAL
        bunch.x -= self.D_x*bunch.dp
        bunch.y -= self.D_y*bunch.dp
        
        self.track_without_dispersion(bunch)
        
        bunch.x += self.D_x*bunch.dp
        bunch.y += self.D_y*bunch.dp
        
    def track_without_dispersion(self, bunch):
        
        #LONGITUDINAL
        bunch.dp -= 2*bunch.dp/self.tau_z
        bunch.dp += 2*self.sigma_dpp0*np.sqrt(1/self.tau_z)*np.random.normal(size=len(bunch.dp))
        bunch.dp -= (self.E_loss_eV*np.abs(bunch.charge))/(bunch.mass*c*c*bunch.gamma)/bunch.beta**2
