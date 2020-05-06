#!/usr/bin/env python3
"""Benchmark on hierarchical clustering methods.
python src/batch.py

"""

import argparse
import logging
from os.path import join as pjoin
from logging import debug, info
import os
import inspect
import numpy as np
import time

import matplotlib; matplotlib.use('Agg')
from matplotlib import pyplot as plt; plt.style.use('ggplot')

import scipy
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import cdist
import pandas as pd

import utils

##########################################################
def extract_features(ouliersdist, avgheight, noutliers, clustids, z):
    clsizes = [0] * 2
    for i in [0, 1]:
        if len(clustids) > i:
            clsizes[i] = len(utils.get_leaves(z, clustids[i]))
            
    features = np.array([ouliersdist, avgheight, noutliers] + clsizes)
    features = np.concatenate((features, z[:, 2]))
    return features

##########################################################
def compute_rel_to_gtruth_difference(accrel, gtruths, distribs, linkagemeths,
        nrealizations):
    diff = {} # difference to the ground-truth
    diffnorms = {}
    for k in distribs:
        diff[k] = dict((el, np.zeros(2)) for el in linkagemeths)
        diffnorms[k] = {}

    for i, distrib in enumerate(distribs):
        for j, linkagemeth in enumerate(linkagemeths):
            diff[distrib][linkagemeth] = gtruths[distrib] - accrel[distrib][linkagemeth]
            diffnorms[distrib][linkagemeth] = np.linalg.norm(diff[distrib][linkagemeth])
    
    winners = {}
    for d in distribs:
        minvalue = 1000
        for l in linkagemeths:
            if diffnorms[d][l] < minvalue:
                winners[d] = l
                minvalue = diffnorms[d][l]
    return diffnorms, winners

##########################################################
def compute_gtruth_vectors(distribs, nrealizations):
    """Compute the ground-truth given by Luc method

    Args:
    data(dict): dict with key 'numclust,method,param' and list as values

    Returns:
    dict: key 'numclust,method,param' and list as values
    """
    gtruths = {}
    for i, k in enumerate(distribs):
        nclusters = int(k.split(',')[0])
        gtruths[k] = np.zeros(2)
        gtruths[k][nclusters-1] = nrealizations

    return gtruths

##########################################################
def export_results(diffnorms, rels, features, distribs, linkagemeths, ndims, outdir):
    df = pd.DataFrame.from_dict(diffnorms, orient='index')
    df['dim'] = pd.Series([ndims for x in range(len(df.index))], index=df.index)
    df.to_csv(pjoin(outdir, 'results.csv'), sep='|', index_label='distrib')

    nrealizations, featsize = features[distribs[0]][linkagemeths[0]].shape
    df = pd.DataFrame.from_dict(features, orient='index')
    # print(nrealizations, featsize)
    # input()

    fh = open(pjoin(outdir, 'features.csv'), 'w')
    header = 'distrib|linkagemeth|realiz|outliersdist|avgheight|noutliers|clsize1|clsize2|'
    header += '|'.join(['h{:03d}'.format(x) for x in range(featsize - 5)])
    print(header, file=fh)
    for l in linkagemeths:
        for d in distribs:
            for r in range(nrealizations):
                s = '{}|{}|{}|'.format(d, l, r)
                s += ('|'.join([str(x) for x in df[l][d][r]]))
                print(s, file=fh)
    fh.close()

##########################################################
def find_clusters_batch(distribs, samplesz, ndims, metric, linkagemeths, clrelsize,
        precthresh, nrealizations, outliersratio, palettehex, outdir):

    info('Computing relevances...')
    minnclusters = 2
    clsize = int(clrelsize * samplesz)

    info('Nrealizations:{}, Samplesize:{}, requestedsz:{}'.\
         format(nrealizations, samplesz, clsize))

    featsize = 5 + (samplesz - 1) # 5 features plus the 2nd column of Z

    rels = {}; methprec = {}; nimprec = {}; features = {}
    for distrib in distribs:
        rels[distrib] = {}; methprec[distrib] = {};
        nimprec[distrib] = {}; features[distrib] = {}
        for l in linkagemeths:
            rels[distrib][l] = [[], []]
            methprec[distrib][l] = []
            nimprec[distrib][l] = 0
            features[distrib][l] = np.zeros((nrealizations, featsize))

    for r in range(nrealizations): # loop realization
        info('realization {:02d}'.format(r))
        data, partsz = utils.generate_data(distribs, samplesz, ndims)

        for j, linkagemeth in enumerate(linkagemeths): # loop method
            for i, distrib in enumerate(data): # loop distrib
                try:
                    z = linkage(data[distrib], linkagemeth, metric)
                except Exception as e:
                    filename = 'error_{}_{}.npy'.format(distrib, linkagemeth)
                    np.save(pjoin(outdir, filename), data[distrib])
                    raise(e)
                maxdist = z[-1, 2]

                ret = utils.find_clusters(data[distrib], z, clsize,
                        minnclusters, outliersratio)
                clustids, avgheight, ouliersdist, outliers = ret
                features[distrib][linkagemeth][r] = \
                        extract_features(ouliersdist, avgheight, len(outliers), clustids, z)

                rel = utils.calculate_relevance(avgheight, ouliersdist, maxdist)
                prec = utils.compute_max_precision(clustids, partsz[distrib], z)
                ngtruth = int(distrib.split(',')[0])
                npred = len(clustids)

                if ngtruth == npred and prec < precthresh: # prec limiarization
                    npred = (npred % 2) + 1
                    nimprec[distrib][linkagemeth] += 1

                rels[distrib][linkagemeth][npred-1].append(rel)

    accrel = utils.accumulate_relevances(rels, distribs, linkagemeths)
    filename = pjoin(outdir, 'nimprec.csv')
    pd.DataFrame(nimprec).to_csv(filename, sep='|', index_label='linkagemeth')

    gtruths = compute_gtruth_vectors(distribs, nrealizations)
    diffnorms, winners = compute_rel_to_gtruth_difference(
            accrel, gtruths, distribs, linkagemeths, nrealizations)

    export_results(diffnorms, rels, features, distribs, linkagemeths, ndims, outdir)
    plot_vectors(rels, accrel, methprec, gtruths, palettehex, outdir)

##########################################################
def plot_vectors(rels, accrel, methprec, gtruths, palettehex, outdir):
    info(inspect.stack()[0][3] + '()')
    distribs = list(rels.keys())
    linkagemeths = list(rels[distribs[0]].keys())
    nrealizations = np.sum([len(g) for g in rels[distribs[0]][linkagemeths[0]]])

    nrows = len(distribs); ncols = 1
    fig, ax = plt.subplots(nrows, ncols, figsize=(ncols*5, nrows*4), squeeze=False)
    palette = utils.hex2rgb(palettehex, alpha=.8)

    origin = np.zeros(2)
    for i, distrib in enumerate(distribs):
        xs = np.array([gtruths[distrib][0]])
        ys = np.array([gtruths[distrib][1]])

        ax[i, 0].quiver(origin, origin, xs, ys, color='#000000', width=.01,
                        angles='xy', scale_units='xy', scale=1, label='Gtruth',
                        headwidth=5, headlength=4, headaxislength=3.5, zorder=3)

        for j, linkagemeth in enumerate(linkagemeths):
            xs = np.array([accrel[distrib][linkagemeth][0]])
            ys = np.array([accrel[distrib][linkagemeth][1]])

            coords = np.array([accrel[distrib][linkagemeth][0],
                              accrel[distrib][linkagemeth][1]])
            ax[i, 0].quiver(origin, origin, xs, ys, color=palette[j], width=.01,
                            angles='xy', scale_units='xy', scale=1,
                            label=linkagemeth,
                            headwidth=5, headlength=4, headaxislength=3.5,
                            zorder=1/np.linalg.norm(coords)+3)

            ax[i, 0].set_xlim(0, nrealizations)
            ax[i, 0].set_ylim(0, nrealizations)
            # ax[i, 0].set_axisbelow(True)
            # ax[i, 0].text(0.5, 0.9, 'prec:{}'.format(
                # np.sum(methprec[distrib][linkagemeth])),
                     # horizontalalignment='center', verticalalignment='center',
                     # fontsize='large')

        # plt.text(0.5, 0.9, 'winner:{}'.format(winner[distrib]),
                 # horizontalalignment='center', verticalalignment='center',
                 # fontsize='large', transform = ax[i, 1].transAxes)

        ax[i, 0].set_ylabel('Sum of relevances of 2 clusters', fontsize='medium')
        ax[i, 0].set_xlabel('Sum of relevances of 1 cluster', fontsize='medium')
        ax[i, 0].legend()

    plt.tight_layout(pad=4)
    utils.export_individual_axis(ax, fig, distribs, outdir, 0.36, 'relev_vector_')

    for i, distrib in enumerate(distribs): # Plot
        ax[i, 0].set_ylabel('{}'.format(distrib), size='x-large')

    plt.savefig(pjoin(outdir, 'relev_vectors_all.pdf'))

##########################################################
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ndims', type=int, default=2, help='Dimensionality')
    parser.add_argument('--samplesz', type=int, default=50, help='Sample size')
    parser.add_argument('--nrealizations', type=int, default=3, help='Sample size')
    parser.add_argument('--outdir', default='/tmp/out/', help='Output directory')
    parser.add_argument('--seed', default=0, type=int)
    args = parser.parse_args()

    logging.basicConfig(format='[%(asctime)s] %(message)s',
                        datefmt='%Y%m%d %H:%M', level=logging.INFO)

    t0 = time.time()

    outdir = pjoin(args.outdir, '{:02}d'.format(args.ndims))
    if not os.path.isdir(outdir): os.makedirs(outdir)
    else: info('Overwriting contents of folder {}'.format(outdir))

    np.random.seed(args.seed)

    # linkagemeths = 'single,complete,average,centroid,median,ward'.split(',')
    linkagemeths = ['single']
    decays = 'uniform,gaussian,power,exponential'.split(',')
    alpha = '4'

    # distribs = [','.join(['1', d]) for d in decays]
    # distribs += [','.join(['2', d, alpha]) for d in decays]
    distribs = ['2,exponential,4']
    metric = 'euclidean'
    pruningparam = 0.02
    clrelsize = 0.3 # cluster rel. size
    precthresh = 0.7
    palettehex = plt.rcParams['axes.prop_cycle'].by_key()['color']
    info('pruningparam:{}'.format(pruningparam))

    find_clusters_batch(distribs, args.samplesz, args.ndims, metric,
            linkagemeths, clrelsize, precthresh,
            args.nrealizations, pruningparam, palettehex, outdir)

    info('Elapsed time:{}'.format(time.time()-t0))
    info('Results are in {}'.format(outdir))

##########################################################
if __name__ == "__main__":
    main()

