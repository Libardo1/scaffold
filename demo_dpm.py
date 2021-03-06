"""
A demonstration of a Dirichlet process binary mixture model, implemented by Gibbs sampling (Neal Algorithm 3)
"""
from __future__ import division
import sys

from numpy import *
from scipy import stats
from scipy import special
import datasources
from datasources import BinomialCluster
import scaffold
import helpers
import runner
from runner import ForEach


gammaln = special.gammaln
betaln = special.betaln

# To use scaffold, you need to inherit from at least two classes: scaffold.State and scaffold.Chain

class State(scaffold.State):
    __slots__ = ['alpha', 'c'] #The state of this Markov chain is fully described by these three values.
    # alpha is the DPM concentration parameter
    # c is a vector, where c[i] is the id of the cluster which datapoint 'i' belongs to.


class BinoChain(scaffold.Chain):

    # You must implement start_state and transition.

    def start_state(self, params, data_params, rng):
        return self.sample_latent(params, data_params, rng) #Here the start state is defined to be a sample from the prior.

    def transition(self, state, params, data, rng):
        n = len(data)
        s = State()
        s.alpha = self.sample_alpha(state, params, n, rng)
        c = copy(state.c)
        for i in range(n):
            c[i] = self.sample_c(i, c, params, data, s.alpha, params['beta'], rng)
        s.c = c
        return s

    # sample_data and sample_latent are optional methods for supporting Geweke testing. You do not have to implement
    # these if you are not going to use the testing functionality.
    def sample_data(self, state, params, data_params, rng):
        _, c = unique(state.c, return_inverse=True)
        n_clusters = len(unique(c))
        clusters = rng.beta(params['beta'], params['beta'], size=n_clusters)
        n = data_params['n']
        dim = data_params['dim']
        x = zeros((n, dim), bool)
        for i in range(n):
            cluster = clusters[c[i]]
            x[i] = rng.random_sample(size=dim) < cluster
        return x


    def sample_latent(self, params, data_params, rng):
        s = State()
        s.alpha = rng.gamma(params['alpha_shape'], scale=params['alpha_scale'])
        n = data_params['n']
        c = zeros(n, int)
        for i in range(1, n):
            c_before = c[:i]
            cluster_ids = unique(c_before)
            p = zeros(len(cluster_ids) + 1)
            for j, cluster_id in enumerate(cluster_ids):
                p[j] = sum(cluster_ids == cluster_id)
            p[-1] = s.alpha
            c[i] = helpers.discrete_sample(p, rng=rng)
        s.c = c
        return s

    # The reminder of the methods are not defined in scaffold.Chain, but are custom to this class. They each
    # implement one component of the Gibbs sampler.

    def sample_alpha(self, state, params, n, rng):
        n_clusters = len(unique(state.c))

        def calc_alpha_llh(alpha):
            prior = stats.gamma.logpdf(alpha, params['alpha_shape'], scale=params['alpha_scale'])
            lh = gammaln(alpha) + n_clusters * log(alpha) - gammaln(alpha + n)
            return prior + lh

        grid = linspace(.1, 10, 1000)
        alpha_llh = calc_alpha_llh(grid)
        alpha = grid[helpers.discrete_sample(alpha_llh, rng=rng, log_mode=True)]
        return alpha

    def sample_c(self, i, c, params, data, dp_alpha, beta, rng, debug=False):
        c_diff = delete(c, i)
        cluster_ids = unique(c_diff)
        n_clusters = len(cluster_ids)
        p = zeros(n_clusters + 1)
        x = data[i].astype(int)
        alpha_set = []
        beta_set = []
        count_set = []
        for j, cluster_id in enumerate(cluster_ids):
            count = sum(c_diff == cluster_id)
            prior = log(count)
            c_in = (c == cluster_id)
            c_in[i] = False
            alpha = beta + sum(data[c_in] == True, 0)
            beta = beta + sum(data[c_in] == False, 0)
            lh = sum(betaln(alpha + x, beta + (1 - x)) - betaln(alpha, beta))
            p[j] = lh + prior
        prior = log(dp_alpha)
        lh = sum(betaln(beta + x, beta - x + 1) - betaln(beta, beta))
        p[-1] = prior + lh
        if debug:
            p_conv = exp(p)
            p_conv /= sum(p_conv)
        idx = helpers.discrete_sample(p, rng=rng, log_mode=True)
        if idx == len(p) - 1:
            c_return = cluster_ids[-1] + 1
        else:
            c_return = cluster_ids[idx]
        if debug:
            return c_return, (p_conv, alpha_set, beta_set, x, count_set)
        else:
            return c_return

# Here we define the synthetic data source we'll be testing on. In this case, it is a finite mixture.
cluster1 = BinomialCluster([.1, .8, .1, .8])
cluster2 = BinomialCluster([.8, .1, .8, .1])


chain = BinoChain(alpha=1, beta=1, alpha_shape=1, alpha_scale=1, beta_shape=2, beta_scale=1 / 2)
dp = dict(n=10, dim=5)


expt = runner.Experiment()

method_conf = dict(chain_class='BinoChain',  alpha_shape=1, alpha_scale=1, beta=1, seed=ForEach([0, 1]), max_iters=50)

data_src_conf = dict(data_class='FiniteMixture', clusters=(cluster1, cluster2), n_points=ForEach([5, 20, 50]), weights=(.5, .5), seed=0)
expt.configure(method_conf, data_src_conf)


def run_expt(): #This function will actually run the experiment and return the results. Results are stored in the runner.History object.
    expt.run(use_cache=False, run_mode='cloud')
    results = expt.fetch_results()
    return results

def run_tests(n=1000): #This function will run a Geweke test to make sure the Gibbs sampler is implemented correctly.
    tests = [lambda state: state.alpha, lambda state: len(unique(state.c)),
             lambda state: state.alpha ** 2]
    z = chain.geweke_test(n, dp, tests)
    return z

if __name__ == "__main__":
    run_expt()