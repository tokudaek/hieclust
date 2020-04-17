#!/usr/bin/env python3
"""Benchmark on hierarchical clustering methods
"""

import argparse
import logging
from os.path import join as pjoin
from logging import debug, info
import os
import time
import numpy as np

import matplotlib; matplotlib.use('Agg')
from matplotlib import pyplot as plt; plt.style.use('ggplot')
import matplotlib.cm as cm
from matplotlib.transforms import blended_transform_factory
from matplotlib.lines import Line2D

from scipy.stats import pearsonr
import pandas as pd

import imageio
import scipy
import inspect
import igraph

import utils

##########################################################
def concat_results(resdir):
    info(inspect.stack()[0][3] + '()')
    filenames = ['resultsall.csv', 'results.csv']

    for f in filenames:
        dfpath = pjoin(resdir, f)
        if os.path.exists(dfpath):
            info('Loading {}'.format(dfpath))
            return pd.read_csv(dfpath, sep='|')

    csvs = []
    for d in os.listdir(resdir):
        respath = pjoin(resdir, d, 'results.csv')
        if not os.path.exists(respath): continue
        csvs.append(pd.read_csv(respath, sep='|'))
    resdf = pd.concat(csvs, axis=0, ignore_index=True)
    resdf.to_csv(dfpath, sep='|', index=False)
    return resdf

##########################################################
def plot_parallel(df, colours, ax, fig):
    dim = df.dim[0]
    df = df.T.reset_index()
    df = df[df['index'] != 'dim']

    ax = pd.plotting.parallel_coordinates(
        df, 'index',
        axvlines_kwds={'visible':True, 'color':np.ones(3)*.6,
                       'linewidth':4, 'alpha': 0.9, },
        ax=ax, linewidth=4, alpha=0.9,
        color = colours,
    )
    ax.yaxis.grid(False)
    ax.xaxis.set_ticks_position('top')
    # ax.set_yticks([0, 100, 200, 300, 400, 500])
    ax.tick_params(axis='y', which='major', labelsize=25)
    ax.set_xticklabels([])
    ax.set_xlim(-.5, 7.5)
    ax.set_ylabel('Accumulated error', fontsize=25)
    ax.spines['right'].set_visible(False)
    ax.spines['top'].set_visible(False)
    ax.spines['bottom'].set_visible(False)

    ax.legend(
        fontsize=25,
        loc=[.82, .28],
    )

    ax.tick_params(bottom="off")
    ax.tick_params(axis='x', length=0)

    # axicon = fig.add_axes([0.4,0.4,0.1,0.1])
    # axicon.imshow(np.random.rand(100,100))
    # axicon.set_xticks([])
    # axicon.set_yticks([])

    trans = blended_transform_factory(fig.transFigure, ax.transAxes) # separator
    line = Line2D([0, .98], [-.05, -.05], color='k', transform=trans)
    plt.tight_layout()
    fig.lines.append(line)

##########################################################
def include_icons(iconpaths, fig):
    for i, iconpath in enumerate(iconpaths):
        # sign = 0.015*(-1) ** i
        sign = 0.0
        im = imageio.imread(iconpath)
        newax = fig.add_axes([0.17+i*.106, 0.79+sign, 0.06, 0.2], anchor='NE', zorder=-1)
        newax.imshow(im, aspect='equal')
        newax.axis('off')

##########################################################
def plot_parallel_all(df, iconsdir, outdir):
    info(inspect.stack()[0][3] + '()')
    if not os.path.isdir(outdir): os.mkdir(outdir)

    colours = cm.get_cmap('tab10')(np.linspace(0, 1, 6))
    dims = np.unique(df.dim)

    figscale = 5
    fig, axs = plt.subplots(len(dims), 1, figsize=(4*figscale, 5*figscale),
                            squeeze=False)

    for i, dim in enumerate(dims):
        slice = df[df.dim == dim]
        slice = slice.set_index('distrib')
        plot_parallel(slice, colours, axs[i, 0], fig)

    # plt.tight_layout(rect=(0.1, 0, 1, 1))
    plt.tight_layout(rect=(0.1, 0, 1, .94), h_pad=.6)
    for i, dim in enumerate(dims):
        plt.text(-0.12, .5, '{}-D'.format(dim),
                 horizontalalignment='center', verticalalignment='center',
                 fontsize='30',
                 transform = axs[i, 0].transAxes
                 )

    iconpaths = [ pjoin(iconsdir, 'icon_' + f + '.png') for f in df[df.dim==2].distrib ]

    include_icons(iconpaths, fig)

    plt.savefig(pjoin(outdir, 'parallel_all.pdf'))

##########################################################
def count_method_ranking(df, linkagemeths, linkagemeth, outdir):
    info(inspect.stack()[0][3] + '()')
    
    methidx = np.where(np.array(linkagemeths) == linkagemeth)[0][0]

    data = []
    for i, row in df.iterrows():
        values = row[linkagemeths].values
        sortedidx = np.argsort(values)
        methrank = np.where(sortedidx == methidx)[0][0]

        data.append([row.distrib, row.dim, methrank])

    methdf = pd.DataFrame(data, columns='distrib,dim,methrank'.split(','))
    ndistribs = len(np.unique(methdf.distrib))

    fh = open(pjoin(outdir, 'meths_ranking.csv'), 'w')
    print('dim,uni,bi', file=fh)
    for d in np.unique(methdf.dim):
        filtered1 = methdf[methdf.dim == d][:4]
        filtered1 = filtered1[(filtered1.methrank < 3)]

        filtered2 = methdf[methdf.dim == d][4:]
        filtered2 = filtered2[(filtered2.methrank < 3)]

        m = methdf[methdf.dim == d]

        # print('dim:{}\t{}/{}\t{}/{}'.format(d, filtered1.shape[0], 4,
                                     # filtered2.shape[0], 4))
        print('{},{},{}'.format(d, filtered1.shape[0], filtered2.shape[0]), file=fh)
    fh.close()

##########################################################
def scatter_pairwise(df, linkagemeths, palettehex, outdir):
    info(inspect.stack()[0][3] + '()')

    nmeths = len(linkagemeths)
    nplots = int(scipy.special.comb(nmeths, 2))

    nrows = nplots;  ncols = 1
    figscale = 4
    fig, axs = plt.subplots(nrows, ncols, squeeze=False,
                            figsize=(ncols*figscale*1.2, nrows*figscale))

    dims = np.unique(df.dim)
    distribs = []
    modal = {1: [], 2:[]}
    for d in np.unique(df.distrib):
        modal[int(d[0])].append(d)

    colours = {c: palettehex[i] for i,c in enumerate(dims)}
    markers = {1:'$1$', 2: '$2$'}

    corr =  np.ones((nmeths, nmeths), dtype=float)
    k = 0
    for i in range(nmeths-1):
        m1 = linkagemeths[i]
        for j in range(i+1, nmeths):
            ax = axs[k, 0]
            m2 = linkagemeths[j]

            for idx, row in df.iterrows():
                dim = row.dim
                nclusters = int(str(row.distrib)[0])
                ax.scatter(row[m1], row[m2], label=str(dim),
                           c=colours[dim], marker=markers[nclusters])

            p = pearsonr(df[m1], df[m2])[0]
            corr[i, j] = p
            corr[j, i] = p

            ax.set_title('Pearson corr: {:.3f}'.format(p))

            from matplotlib.patches import Patch
            legend_elements = [   Patch(
                                       facecolor=palettehex[dimidx],
                                       edgecolor=palettehex[dimidx],
                                       label=str(dims[dimidx]),
                                       )
                               for dimidx in range(len(dims))]

            # Create the figure
            ax.legend(handles=legend_elements, loc='lower right')
            # breakpoint()
            
            # ax.legend(title='Dimension', loc='lower right')
            ax.set_xlabel(m1)
            ax.set_ylabel(m2)
            ax.set_ylabel(m2)
            k += 1

    plt.tight_layout(pad=1, h_pad=3)
    plt.savefig(pjoin(outdir, 'meths_pairwise.pdf'))
    return corr

##########################################################
def plot_meths_heatmap(methscorr, linkagemeths, label, outdir):
    info(inspect.stack()[0][3] + '()')

    n = methscorr.shape[0]

    fig, ax = plt.subplots(figsize=(5, 4))
    im = ax.imshow(methscorr, cmap='coolwarm', vmin=-1, vmax=1)

    ax.set_xticks(np.arange(len(linkagemeths)))
    ax.set_yticks(np.arange(len(linkagemeths)))
    ax.set_xticklabels(linkagemeths)
    ax.set_yticklabels(linkagemeths)
    ax.grid(False)

    plt.setp(ax.get_xticklabels(), rotation=45, ha="right",
             rotation_mode="anchor")

    for i in range(n):
        for j in range(i+1, n):
            text = ax.text(j, i, '{:.2f}'.format(methscorr[i, j]),
                           ha="center", va="center", color="k")


    # ax.set_title("Pairwise pearson correlation between linkage methods")

    # Create colorbar
    cbar = ax.figure.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.ax.set_ylabel('pearson corr.', rotation=-90, va="bottom")
    fig.tight_layout(pad=0.5)
    plt.savefig(pjoin(outdir, 'meths_heatmap_' + label + '.pdf'))

##########################################################
def plot_graph(methscorr_in, linkagemeths, palettehex, label, outdir):
    """Plot the graph according to the weights.
    However, this is an ill posed problem because
    the weights would need to satisfy the triangle
    inequalities to allow this.

    Args:
    methscorr(np.ndarray): weight matrix
    linkagemeths(list of str): linkage methods
    outdir(str): output dir
    """
    info(inspect.stack()[0][3] + '()')

    methscorr = np.abs(methscorr_in)
    n = methscorr.shape[0]
    g = igraph.Graph.Full(n, directed=False, loops=False)

    min_, max_ = np.min(methscorr), np.max(methscorr)
    range_ = max_ - min_

    todelete = []
    widths = []
    for i in range(g.ecount()):
        e = g.es[i]
        c = methscorr[e.source, e.target]
        v = (c - min_) / range_
        if v > .3:
            g.es[i]['weight'] = (c - min_) / range_
            widths.append(10*g.es[i]['weight'])
        else:
            todelete.append(i)
    g.delete_edges(todelete)

    g.vs['label'] = linkagemeths
    # g.vs['label'] = ['     ' + l for l in linkagemeths]
    edgelabels = ['{:.2f}'.format(x) for x in g.es['weight']]
    # l = igraph.GraphBase.layout_fruchterman_reingold(weights=g.es['weight'])
    palette = utils.hex2rgb(palettehex, alpha=.8)
    l = g.layout('fr', weights=g.es['weight'])
    outpath = pjoin(outdir, 'meths_graph_' + label + '.pdf')
    vcolors = palettehex[:g.vcount()]

    igraph.plot(g, outpath, layout=l,
                edge_label=edgelabels, edge_width=widths,
                edge_label_size=15,
                vertex_color=vcolors, vertex_frame_width=0,
                vertex_label_size=30,
                margin=80)

##########################################################
def plot_pca(featurespath):
    df = pd.read_csv(featurespath, sep='|')
    cols = []
    for col in df.columns:
        if col.startswith('h'):
            cols.append(col)

    # print(df.distrib)
    # print(df.linkagemeth)
    print(df.distrib)
    df = df[df.distrib=='1,uniform'] # filter
    print(df.shape)
    df = df[df.linkagemeth == 'single'] # filter
    print(df.shape)
    input()
    x, evecs, evals = pca(df[cols].values)
    # distribs = np.unique(df.distrib)
    # for distrib in distribs:
    plt.scatter(x[:, 0], x[:, 1], label=distrib)

    # plt.scatter(x[:, 0], x[:, 1], label=df.distrib.values)
    plt.legend()
    plt.savefig('/tmp/out.png')
    # pca()
    # return

##########################################################
def pca(xin):
    x = xin - np.mean(xin, axis=0)
    cov = np.cov(x, rowvar = False)
    evals , evecs = np.linalg.eig(cov)

    idx = np.argsort(evals)[::-1]
    evecs = evecs[:,idx] # each column is a eigenvector
    evals = evals[idx]
    a = np.dot(x, evecs)
    return a, evecs, evals

##########################################################
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pardir', default='/tmp/',
            help='Path to the folder containing results[all].csv')
    args = parser.parse_args()

    logging.basicConfig(format='[%(asctime)s] %(message)s',
                        datefmt='%Y%m%d %H:%M', level=logging.INFO)

    t0 = time.time()
    outdir = pjoin(args.pardir, 'figsresults/')
    iconsdir = pjoin(args.pardir, 'figsarticle/')

    if not os.path.isdir(outdir): os.mkdir(outdir)
    if not os.path.isdir(iconsdir):
        info('Icons path {} does not exist,'.format(iconsdir));
        info('run src/createfigures.py first!');
        return

    np.random.seed(0)

    palettehex = plt.rcParams['axes.prop_cycle'].by_key()['color']

    resdf = concat_results(args.pardir)

    #TODO: load from resdir folder
    distribs = np.unique(resdf.distrib)
    linkagemeths = resdf.columns[1:-1]
    clrelsize = .3
    pruningparam = .02

    plot_parallel_all(resdf, iconsdir, outdir)
    count_method_ranking(resdf, linkagemeths, 'single', outdir)
    for nclusters in ['1', '2']:
        filtered = resdf[resdf['distrib'].str.startswith(nclusters)]
        methscorr = scatter_pairwise(filtered, linkagemeths, palettehex, outdir)
        plot_meths_heatmap(methscorr, linkagemeths, nclusters, outdir)
        plot_graph(methscorr, linkagemeths, palettehex, nclusters, outdir)
    info('Elapsed time:{}'.format(time.time()-t0))
    info('Results are in {}'.format(outdir))
    # featurespath = pjoin(outdir)
    # plot_pca(featurespath)
    # return

##########################################################
if __name__ == "__main__":
    main()

