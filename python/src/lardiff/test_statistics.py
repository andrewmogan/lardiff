import numpy as np
from scipy import fftpack
from scipy import stats

from functools import lru_cache
from scipy.stats import rv_continuous, chi2, ttest_ind, chisquare
from scipy.special import erf, erfinv
from scipy.optimize import root_scalar

from .consts import *
from .waveform_functions import smear_signal, convolve, \
     deconvolve, coarsen_signal, fix_baseline, shift_signal_1D

def calc_test_statistic(input_sig, 
                        anode_hist, anode_uncert_hist, 
                        cathode_hist, cathode_uncert_hist, 
                        dl_hyp, dt_hyp, 
                        test_statistic):

    temp_test_stat  = None 
    temp_num_values = None 
    shift_vector    = None
    if test_statistic == "chi2":
        temp_test_stat, temp_num_values, shift_vector = calc_chisq(
            input_sig, 
            anode_hist, anode_uncert_hist, 
            cathode_hist, cathode_uncert_hist, 
            dl_hyp, dt_hyp, 
        )
    elif test_statistic == "invariant3":
        print('Oops not yet implemented')
    else:
        raise ValueError('Invalid test_statistic argument provided')

    return temp_test_stat, temp_num_values, shift_vector

# Calculate one chi-squared point given value of DL and DT and 2D distributions associated with specific track data angle bin
def calc_chisq(input_sig, anode_hist, anode_uncert_hist, cathode_hist, cathode_uncert_hist, DL_hyp, DT_hyp):
    sig_A = smear_signal(input_sig, ticks_drift_A, DL_hyp, DT_hyp)
    sig_C = smear_signal(input_sig, ticks_drift_C, DL_hyp, DT_hyp)
    sig_A_coarse = coarsen_signal(sig_A)
    sig_C_coarse = coarsen_signal(sig_C)

    pred_hist = np.zeros((N_ticks, N_wires))
    pred_uncert_hist = np.zeros((N_ticks, N_wires))
    for col in range(0, N_wires):
        sig_A_slice = sig_A_coarse[:, col]
        sig_A_slice = sig_A_slice / sig_A_slice.sum()
        sig_C_slice = sig_C_coarse[:, col]
        sig_C_slice = sig_C_slice / np.real(sig_C_slice).sum()
        diffusion_kernel = deconvolve(sig_C_slice, sig_A_slice)

        anode_slice = anode_hist[:, col]
        anode_uncert_slice = anode_uncert_hist[:, col]

        pred_slice = convolve(anode_slice, diffusion_kernel)
        pred_uncert_slice = convolve(anode_uncert_slice, diffusion_kernel)

        pred_hist[:, col] = np.real(pred_slice)
        pred_uncert_hist[:, col] = np.real(pred_uncert_slice)

    pred_hist = fix_baseline(pred_hist, anode_hist)
    pred_uncert_hist = fix_baseline(pred_uncert_hist, anode_uncert_hist)

    cathode_max = 0.0
    for col in range(((N_wires-1)//2)-((N_wires_fit-1)//2), ((N_wires-1)//2)+((N_wires_fit-1)//2)+1):
        for row in range(((N_ticks-1)//2)-((N_ticks_fit-1)//2), ((N_ticks-1)//2)+((N_ticks_fit-1)//2)+1):
            if col == (N_wires-1)//2: continue
            if cathode_hist[row,col] < cathode_max: continue
            cathode_max = cathode_hist[row,col]

    chisq = 0.0
    numvals = 0.0
    shift_vec = np.zeros((N_wires))
    for col in range(((N_wires-1)//2)-((N_wires_fit-1)//2), ((N_wires-1)//2)+((N_wires_fit-1)//2)+1):

        # Skip central wire to avoid bias (I think?)
        if col == (N_wires-1)//2: continue

        min_chisq = np.inf
        min_numvals = 0.0
        for shift_val in np.arange(-1.0*shift_max, shift_max+shift_step, shift_step):
            anode_norm = 0
            pred_norm = 0
            cathode_norm = 0
            pred_hist_1D_shifted = shift_signal_1D(pred_hist[:, col], shift_val)
            pred_uncert_hist_1D_shifted = shift_signal_1D(pred_uncert_hist[:, col], shift_val)
            for row in range(((N_ticks-1)//2)-((N_ticks_fit-1)//2), ((N_ticks-1)//2)+((N_ticks_fit-1)//2)+1):

                if cathode_hist[row,col] < threshold_rel*cathode_max: continue

                anode_norm += anode_hist[row,col]
                pred_norm += pred_hist_1D_shifted[row]
                cathode_norm += cathode_hist[row,col]

            chisq_temp = 0.0
            numvals_temp = 0.0
            for row in range(((N_ticks-1)//2)-((N_ticks_fit-1)//2), ((N_ticks-1)//2)+((N_ticks_fit-1)//2)+1):

                if cathode_hist[row,col] < threshold_rel*cathode_max: continue

                chisq_temp += ((pred_hist_1D_shifted[row]/pred_norm - cathode_hist[row,col]/cathode_norm)**2) / \
                              ((pred_uncert_hist_1D_shifted[row]/pred_norm)**2 + (cathode_uncert_hist[row,col]/cathode_norm)**2)
                numvals_temp += 1.0
            if chisq_temp < min_chisq:
                min_chisq = chisq_temp
                min_numvals = numvals_temp
                shift_vec[col] = shift_val
        chisq += min_chisq
        numvals += min_numvals
                
    return chisq, numvals, shift_vec

### Invariant3 functions as given in 
### https://journals.aps.org/prd/abstract/10.1103/PhysRevD.103.113008 

class Bee(rv_continuous):
    def _cdf(self, x, df):
        return erf(x/np.sqrt(2))**df
    def _pdf(self, x, df):
        ret = df*(erf(x/np.sqrt(2)))**(df-1)
        return ret * np.sqrt(2/np.pi)*np.exp(-x**2/2)
    def ppf(self, x, df):
        return erfinv((x)**(1/df)) * np.sqrt(2)
    
class BeeSquared(rv_continuous):
    def _cdf(self, x, df):
        b = np.sqrt(x)
        ret = bee.cdf(b, df)
        return ret
    def _pdf(self, x, df):
        ret = df*(erf(np.sqrt(x/2)))**(df-1)
        return ret / np.sqrt(2*np.pi*x) * np.exp(-x/2)
    def ppf(self, x, df):
        b = bee.ppf(x, df)
        return b**2

@np.vectorize
@lru_cache(10000)
def _yfrommax(b, df = 2, alpha = 0.5):
    """(1—diagonal coordinate) from (1—max) of accepted region"""
    # A=(1-b)**df—((y-b)**df)/((1-alpha+alpha*y)**(df-1))=1—y
    beta = 1 - alpha
    q=(1.0-b) ** df-1
    dfm=df-1
    def f(y):
        return q-((y-b) ** df) / ((beta + alpha * y) ** (dfm)) + y
    if b <=0:
        return 0.0
    if b >= 1:
        return 1.0
    else:
        return root_scalar(f, x0=b, x1 = b * 1.001).root

def yfrommax(b, df = 2, alpha = 0.5):
    """Buffer and interpolate values to speed things up."""
    step = 0.0001
    b_= np.floor(b / step, dtype=float) * step
    b__= b_ + step
    delta = (b-b_) / step
    x_  = _yfrommax(b_,  df = df, alpha = alpha)
    x__ = _yfrommax(b__, df = df, alpha = alpha)
    return x_+(x__ - x_) * delta

def invariant3(x, alpha = 0.5, fast = False):
    """Return test statistic given vector of normalized values."""
    if fast:
        sf = 1 - chi2.cdf(x ** 2, df = 1) # Faster, but less accurate
    else:
        sf = chi2.sf(x ** 2, df = 1)
    # Get possible diagonal coordinate from maximum CDF value (= minimum SF)
    a = np.min(sf, axis=-1)
    b = np.max(sf, axis=-1)
    yfm = yfrommax(a, df=x.shape[-1], alpha = alpha)
    # Get possible diagonal coordinate from center surface
    yfc = (alpha * (a - b) + b) / (1.0 + alpha * (a - b))
    y = np.minimum(yfc, yfm)
    y = np.maximum(y, 0) # Cap in case of rounding or root finding errors
    return chi2.isf(y, df = 1)



