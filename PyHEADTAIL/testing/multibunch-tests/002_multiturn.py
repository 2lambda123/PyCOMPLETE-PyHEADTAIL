import matplotlib.pyplot as plt
import numpy as np
import os
from scipy.constants import c, e, m_p
from scipy.signal import fftconvolve
import time

from PyHEADTAIL.particles.slicing import UniformBinSlicer
from PyHEADTAIL.particles.particles import Particles
# from PyHEADTAIL.impedances.wakes import CircularResistiveWall, WakeField
from PyHEADTAIL.impedances.wakes import CircularResonator, WakeField
from PyHEADTAIL.monitors.monitors import BunchMonitor
from PyHEADTAIL.machines.synchrotron import Synchrotron


# Machine settings
n_turns = 300

n_macroparticles = 100000 # per bunch
intensity = 2.3e11

alpha = 53.86**-2

p0 = 7000e9 * e / c

accQ_x = 0.31
accQ_y = 0.32
Q_s = 2.1e-3
chroma = 0

circumference = 26658.883 / 35640 * 20

beta_x = 100 #circumference / (2.*np.pi*accQ_x)
beta_y = 100 #circumference / (2.*np.pi*accQ_y)

h_RF = 20
h_bunch = 20

epsn_x = 2e-6
epsn_y = 2e-6
sigma_z = 0.09

machine = Synchrotron(
        optics_mode='smooth', circumference=circumference,
        n_segments=1, s=None, name=None,
        alpha_x=None, beta_x=beta_x, D_x=0,
        alpha_y=None, beta_y=beta_y, D_y=0,
        accQ_x=accQ_x, accQ_y=accQ_y, Qp_x=chroma, Qp_y=chroma,
        app_x=0, app_y=0, app_xy=0,
        alpha_mom_compaction=alpha, longitudinal_mode='linear',
        h_RF=np.atleast_1d(h_RF), p0=p0,
        charge=e, mass=m_p, wrap_z=False, Q_s=Q_s)

transverse_map = machine.transverse_map.segment_maps[0]

# Filling scheme

bunch_spacing_buckets = 5
n_bunches = 3
filling_scheme = [i*bunch_spacing_buckets for i in range(n_bunches)]

# Initialise beam
allbunches = machine.generate_6D_Gaussian_bunch(n_macroparticles, intensity,
                                                epsn_x, epsn_y, sigma_z=sigma_z,
                                                filling_scheme=filling_scheme,
                                                matched=False)

bucket_id_set = list(set(allbunches.bucket_id))

bucket_length = machine.circumference / h_RF
z_all = -allbunches.bucket_id * bucket_length + allbunches.z

amplitude = 1e-3
wavelength = 2
allbunches.x = amplitude * np.sin(2 * np.pi * z_all / wavelength)
allbunches.xp *= 0

# allbunches.x[allbunches.z < 0] = 0

for b_id in bucket_id_set:
    mask = allbunches.bucket_id == b_id
    z_centroid = np.mean(allbunches.z[mask])
    z_std = np.std(allbunches.z[mask])
    mask_tails = mask & (np.abs(allbunches.z - z_centroid) > z_std)
    allbunches.x[mask_tails] = 0
    # if b_id != 0:
    #     allbunches.x[mask] = 0

beam = Particles(macroparticlenumber=allbunches.macroparticlenumber,
                 particlenumber_per_mp=allbunches.particlenumber_per_mp,
                 charge=allbunches.charge, mass=allbunches.mass,
                 circumference=allbunches.circumference, gamma=allbunches.gamma,
                 coords_n_momenta_dict=dict(x=allbunches.x.copy(),
                                            y=allbunches.y.copy(),
                                            xp=allbunches.xp.copy(),
                                            yp=allbunches.yp.copy(),
                                            z=z_all.copy(),
                                            dp=allbunches.dp.copy(),
                 ))

# Initialise wakes

n_slices = 100
slicer = UniformBinSlicer(n_slices, z_cuts=(-0.5*bucket_length, 0.5*bucket_length),
                          circumference=machine.circumference, h_bunch=h_bunch)

n_turns_wake = 3

# pipe radius [m]
b = 13.2e-3
# length of the pipe [m]
L = 100000.
# conductivity of the pipe 1/[Ohm m]
sigma = 1. / 7.88e-10

# wakes = CircularResistiveWall(b, L, sigma, b/c, beta_beam=machine.beta)
wakes = CircularResonator(R_shunt=135e6, frequency=1.97e9*0.6, Q=31000/100, n_turns_wake=n_turns_wake)

# mpi_settings = 'circular_mpi_full_ring_fft'
# wake_field = WakeField(slicer, wakes, mpi=mpi_settings, Q_x=accQ_x, Q_y=accQ_y, beta_x=beta_x, beta_y=beta_y)

mpi_settings = False
# mpi_settings = 'memory_optimized'
wake_field = WakeField(slicer, wakes, mpi=mpi_settings)

# Wake full beam

n_buckets_slicer = max(filling_scheme) + 2
n_buckets_slicer = max(filling_scheme) + 1

slicer_full_beam = UniformBinSlicer(n_buckets_slicer * slicer.n_slices,
                                    z_cuts=((0.5 - n_buckets_slicer)*bucket_length, 0.5*bucket_length),
                                    circumference=machine.circumference, h_bunch=h_bunch)
slicer_full_beam.force_absolute = True

wakes_full_beam = CircularResonator(R_shunt=wakes.R_shunt, frequency=wakes.frequency, Q=wakes.Q, n_turns_wake=wakes.n_turns_wake)
wake_field_full_beam = WakeField(slicer_full_beam, wakes_full_beam, mpi=False)


# import pdb
# pdb.set_trace()

plt.close('all')

fig0, (ax00, ax01) = plt.subplots(2, 1)
ax01.sharex(ax00)

skip = 10
ax00.plot(z_all[::skip], allbunches.x[::skip], '.')
ax00.plot(beam.z[::skip], beam.x[::skip], '.')

x_at_wake_allbunches = []
xp_before_wake_allbunches = []
xp_after_wake_allbunches = []

x_at_wake_beam = []
xp_before_wake_beam = []
xp_after_wake_beam = []

n_turns = 3
color_list = ['r', 'g', 'b', 'c', 'm', 'y', 'k']
for i_turn in range(n_turns):

    x_at_wake_allbunches.append(allbunches.x.copy())
    xp_before_wake_allbunches.append(allbunches.xp.copy())

    x_at_wake_beam.append(beam.x.copy())
    xp_before_wake_beam.append(beam.xp.copy())

    wake_field.track(allbunches)
    wake_field_full_beam.track(beam)

    xp_after_wake_allbunches.append(allbunches.xp.copy())
    xp_after_wake_beam.append(beam.xp.copy())

    transverse_map.track(allbunches)
    transverse_map.track(beam)

    ax00.plot(beam._slice_sets[slicer_full_beam].z_centers, beam._slice_sets[slicer_full_beam].mean_x, 'o')

    #ax01.plot(beam._slice_sets[slicer_full_beam].z_centers, wake_field_full_beam.wake_kicks[0]._last_dipole_kick[0], 'x')

    ax01.plot(z_all[::skip],
              xp_after_wake_allbunches[-1][::skip] - xp_before_wake_allbunches[-1][::skip],
              '.', label=f'MB turn {i_turn}', color=color_list[i_turn])
    ax01.plot(beam.z[::skip], xp_after_wake_beam[-1][::skip] - xp_before_wake_beam[-1][::skip],
              'x', label=f'SB turn {i_turn}', color=color_list[i_turn])

ax01.legend()

plt.show()

sdfkjn

wake_function_x = wake_field_full_beam.wake_kicks[0].wake_function

z_centers = beam._slice_sets[slicer_full_beam].z_centers
dz = z_centers[1] - z_centers[0]

dxp_ref = wake_field_full_beam.wake_kicks[0]._last_dipole_kick[0]
z_ref = z_centers

z_centers_time_sorted = z_centers[::-1]

##############
# Build wake #
##############

# Wake formula
p0_SI = machine.p0
mean_x_slice = beam._slice_sets[slicer_full_beam].mean_x
num_charges_slice = beam._slice_sets[slicer_full_beam].charge_per_slice/e

n_wake = len(z_centers) + 100
z_wake = np.arange(0, -(n_wake)*dz, -dz)[::-1] # HEADTAIL order (time reversed)
assert len(z_wake) == n_wake

z_wake_time_sorted = z_wake[::-1]


R_s = wakes.R_shunt
Q = wakes.Q
f_r = wakes.frequency
omega_r = 2 * np.pi * f_r
alpha_t = omega_r / (2 * Q)
omega_bar = np.sqrt(omega_r**2 - alpha_t**2)
W_r = (R_s * omega_r**2 / (Q * omega_bar) * np.exp(alpha_t * z_wake / c)
      * np.sin(omega_bar * z_wake / c))# Wake definition
W_scaled = -e**2 / (p0_SI * c) * W_r # Put all constants in front of the wake

# Plot wakes
fig10 = plt.figure(10)
ax10 = fig10.add_subplot(111)

ax10.plot(z_wake, W_scaled, label='Wake')
ax10.set_xlabel('z [m]')
ax10.set_ylabel('W(z)')

# Compute dipole moments
dip_moment_slice = num_charges_slice * mean_x_slice

###################################
# Convolution with HEADTAIL order #
###################################
dxp = fftconvolve(dip_moment_slice, W_scaled, mode='full')
# Keep only the last n_centers points
dxp = dxp[-len(z_centers):]

######################################
# Convolution with time sorted order #
######################################

W_scaled_time_sorted = W_scaled[::-1]
dip_moment_slice_time_sorted = dip_moment_slice[::-1]

dxp_time_sorted = np.convolve(
    dip_moment_slice_time_sorted, W_scaled_time_sorted, mode='full')
# Keep only the first n_centers points
dxp_time_sorted = dxp_time_sorted[:len(z_centers)]

# Back to HEADTAIL order
dxp_time_sorted = dxp_time_sorted[::-1]

########################
# Convolution with FFT #
########################

from numpy.fft import fft, ifft

len_fft = len(W_scaled)+len(dip_moment_slice)-1

dxp_fft_time_sorted = ifft(
    fft(W_scaled_time_sorted, n=len_fft)
    * fft(dip_moment_slice_time_sorted, n=len_fft)).real
# Keep only the first n_centers points
dxp_fft_time_sorted = dxp_fft_time_sorted[:len(z_centers)]

# Back to HEADTAIL order
dxp_fft = dxp_fft_time_sorted[::-1]

#######################
# Chopped and compressed convolution #
#######################

K_period = n_slices * bunch_spacing_buckets
L_preserve = n_slices


n_periods = len(W_scaled_time_sorted) // K_period

WWchop = np.zeros_like(W_scaled_time_sorted)
WW_compressed = []
WW = W_scaled_time_sorted
dip_moments_compressed_time_sorted = []
z_centers_compressed_time_sorted = []
z_wake_time_sorted_compressed = []
for ii in range(n_periods+1):
    # part_preserve = slice(ii*K_period - (L_preserve - 1),
    #                       ii*K_period + L_preserve)
    start_preserve = ii*K_period - L_preserve + 1
    if start_preserve < 0:
        start_preserve = 0
    end_preserve = ii*K_period + L_preserve
    if end_preserve > len(W_scaled_time_sorted):
        end_preserve = len(W_scaled_time_sorted)
    part_preserve = slice(start_preserve, end_preserve)
    WWchop[part_preserve] = WW[part_preserve]

    WW_compressed.append(WW[part_preserve])
    z_wake_time_sorted_compressed.append(z_wake_time_sorted[part_preserve])

    dip_moments_compressed_time_sorted.append(
            dip_moment_slice_time_sorted[part_preserve])
    z_centers_compressed_time_sorted.append(z_centers_time_sorted[part_preserve])



W_scaled_time_sorted_chopped = WWchop
W_scaled_time_sorted_compressed = np.concatenate(WW_compressed)
z_wake_time_sorted_compressed = np.concatenate(z_wake_time_sorted_compressed)

dip_moments_compressed_time_sorted = np.concatenate(dip_moments_compressed_time_sorted)
z_centers_compressed_time_sorted = np.concatenate(z_centers_compressed_time_sorted)

ax10.plot(z_wake, W_scaled_time_sorted_chopped[::-1], label='Wake chopped')
ax10.plot(z_wake_time_sorted_compressed, W_scaled_time_sorted_compressed, label='Wake compressed')


len_fft = len(W_scaled_time_sorted_chopped)+len(dip_moment_slice)-1

dxp_fft_time_sorted = ifft(
    fft(W_scaled_time_sorted_chopped, n=len_fft)
    * fft(dip_moment_slice_time_sorted, n=len_fft)).real
# Keep only the first n_centers points
dxp_fft_time_sorted_chopped = dxp_fft_time_sorted[:len(z_centers)]

# Back to HEADTAIL order
dxp_chopped = dxp_fft_time_sorted_chopped[::-1]

###################
# Compressed mode #
###################

len_fft_compressed = len(W_scaled_time_sorted_compressed)+len(dip_moments_compressed_time_sorted)-1

dxp_fft_compressed_time_sorted = ifft(
    fft(W_scaled_time_sorted_compressed, n=len_fft_compressed)
    * fft(dip_moments_compressed_time_sorted, n=len_fft_compressed)).real

# Keep only the first n_centers_compressed points
dxp_fft_compressed_time_sorted = dxp_fft_compressed_time_sorted[:len(z_centers_compressed_time_sorted)]

# Back to HEADTAIL order
dxp_compressed = dxp_fft_compressed_time_sorted[::-1]
z_centers_compressed = z_centers_compressed_time_sorted[::-1]

# Plot results

fig2 = plt.figure(2, figsize=(6.4*1.4, 4.8*1.4))
ax21 = fig2.add_subplot(311)
ax22 = fig2.add_subplot(312, sharex=ax21)
ax23 = fig2.add_subplot(313, sharex=ax21)

ax21.plot(z_centers, num_charges_slice, label='num. charges')
ax21.set_ylabel('Number of charges per slice')
ax22.plot(z_centers, amplitude * np.sin(2 * np.pi * z_centers / wavelength), '--')
ax22.plot(z_centers, mean_x_slice, label='mean x')

ax22.set_ylabel('Mean x per slice')

ax23.plot(z_ref, dxp_ref, label='ref.')
ax23.plot(z_centers, dxp, '--', label='conv.')
ax23.plot(z_centers, dxp_time_sorted, '--', label='conv. t-sorted')
ax23.plot(z_centers, dxp_fft, '--', label='conv. fft')
ax23.plot(z_centers, dxp_chopped, '--', label='conv. chopped')
ax23.plot(z_centers_compressed, dxp_compressed, '--', label='conv. compressed')
ax23.set_ylabel('Dipole kick per slice')
ax23.set_xlabel('z [m]')


# Put legend outside of the plot
plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.)
plt.subplots_adjust(right=0.75, hspace=0.3)

plt.show()
