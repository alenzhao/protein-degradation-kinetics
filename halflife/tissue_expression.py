#!/usr/bin/env python3

import ixntools as ix
from expression import paxdb, proteomicsdb, proteomicsdb_requests as req
from halflife import utils

import numpy as np
from scipy.stats import binom_test
from collections import namedtuple

import logging
import sys

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
log = logging.getLogger('tissue')

def protein_map(species):
    """Returns dictionary of uniprot accession codes to ensp IDs."""
    if species == 'mouse':
        filename = 'data/mouse_uniprot_ensp.txt'
    elif species == 'human':
        filename = 'data/human_uniprot_ensp.txt'
    with open(filename) as infile:
        data = [line.split() for line in infile]
    prot_map = {}
    for line in data:
        if line[0] not in prot_map:
            prot_map[line[0]] = [line[1]]
        else:
            prot_map[line[0]].append(line[1])
    return prot_map

def load_paxdb_data(species):
    if species == 'mouse':
        data = load_ned_data('data/NED_mouse_Abund.txt')[1]
        meta = paxdb.get_metadata('10090')
        pmap = protein_map('mouse')
    elif species == 'human':
        data = load_ned_data('data/NED_human_Abund.txt')[1]
        meta = paxdb.get_metadata('9606')
        pmap = protein_map('human')
    skip = ['CELL_LINE']
    for i in skip:
        meta.pop(i)
    abunds = [paxdb.Abundances(meta[t]['filename'], 0) for t in sorted(meta)]
    header = '\t'.join(['prot', '\t'.join(sorted(meta)), 'tcount', 'def'])
    return header, data, abunds, pmap

def print_expression_data(species):
    header, data, abunds, pmap = load_expression_data(species)
    ofname = 'data/{0}_paxdb_tissue_expression.txt'.format(species)
    with open(ofname, 'w') as outfile:
        outfile.write(header + '\n')
        for line in data:
            if line[0] not in pmap:
                continue
            # list of lists containing tissue expressions for each ensp isoform
            ensps = [[t.data.get(p, 'NA') for t in abunds]
                     for p in pmap[line[0]]]
            ensps = [i for i in ensps if i.count('NA') != len(i)]
            if len(ensps) == 0:
                continue
            # Sort by max tcount, then max avg abundance
            skey = lambda x: (x.count('NA'),
                              -np.mean([p for p in x if p != 'NA']))
            ensps.sort(key=skey)
            expression = '\t'.join([str(e) for e in ensps[0]])
            tcount = str(len(ensps[0]) - ensps[0].count('NA'))
            newline = '\t'.join([line[0], expression, tcount, line[-1]])
            outfile.write(newline + '\n')

def load_proteomicsdb_data():
    data = load_ned_data('data/NED_human.txt')[1]
    isoab = proteomicsdb.Abundances('human_protdb_isoforms_expression.txt')
    abunds = proteomicsdb.Abundances('trembl_tissues.txt')
    tissues = abunds.tissues
    ttargets = ['B-lymphocyte', 'adipocyte', 'adrenal gland', 'brain',
                'colon', 'colonic epithelial cell', 'colorectal cancer cell',
                'cytotoxic T-lymphocyte', 'esophagus', 'gall bladder', 'gut',
                'heart', 'helper T-lymphocyte', 'ileum epithelial cell',
                'liver', 'lung', 'lymph node', 'monocyte', 'myometrium',
                'natural killer cell', 'ovary', 'pancreas',
                'pancreatic islet', 'placenta', 'prostate gland', 'rectum',
                'retina', 'stomach', 'testis', 'thyroid gland',
                'salivary gland', 'spinal cord', 'spleen', 'tonsil',
                'urinary bladder', 'uterine cervix', 'uterus']
    header = '{0}\t{1}\t{2}\t{3}\n'.format('prot', '\t'.join(ttargets),
                                           'tcount', 'def')
    with open('data/human_protdb_limited_tissues.txt', 'w') as outfile:
        outfile.write(header)
        for line in data:
            prot = line[0]
            if prot in abunds.proteins:
                expression = [abunds.expression(prot, tis) for tis in ttargets]
            elif prot in isoab.proteins:
                expression = [isoab.expression(prot, tis) for tis in ttargets]
            else:
                continue
            tcount = str(len(expression) - expression.count('NA'))
            newline = '\t'.join([prot] + expression + [tcount, line[-1]])
            outfile.write(newline + '\n')

def tcount_binomial_test():
    fname = 'data/abundance/human_proteomicsdb_tissue_expression.txt'
    with open(fname) as infile:
        data = [line.strip().split('\t') for line in infile]
    data = {line[0]: [int(line[-2]),  line[-1]] for line in data[1:]}
    core = ix.dbloader.LoadCorum('Human', 'core')
    success, trials = 0, 0
    for struc in core.strucs:
        nvals = []
        evals = []
        subunits = core[struc].uniprot
        for sub in subunits:
            if len(sub) == 1 and sub[0] in data:
                if data[sub[0]][1] == 'NED':
                    nvals.append(data[sub[0]][0])
                elif data[sub[0]][1] == 'ED':
                    evals.append(data[sub[0]][0])
            else:
                for p in sub:
                    if p in data and data[p][1] == 'NED':
                        nvals.append(data[p][0])
                        break
                    elif p in data and data[p][1] == 'ED':
                        evals.append(data[p][0])
                        break
        if len(evals) > 0 and len(nvals) > 0:
            trials += 1
            if np.mean(nvals) >= np.mean(evals):
                success += 1
    print(success, trials, binom_test(success, trials))

def abundance_binomial_test(species, homologs=False):
    header, data = load_ned_data('data/NED_{0}_Abund.txt'.format(species))
    Prot = namedtuple('Prot', ['abundance', 'decay'])
    if homologs == True:
        core = ix.dbloader.LoadCorum('Human', 'core')
        homs = map_mouse_homologs()
        prots = {homs[line[-2]]: Prot(np.log(float(line[-4])), line[-3])
                 for line in data if line[-2] in homs}
    else:
        core = ix.dbloader.LoadCorum(species.title(), 'core')
        prots = {line[-2]: Prot(float(line[-4]), line[-3]) for line in data}
    success, trials = 0, 0
    for struc in core.strucs:
        nvals = []
        evals = []
        subunits = core[struc].uniprot
        for sub in subunits:
            # Deals with ambiguous (bracketed) subunits
            if len(sub) == 1 and sub[0] in prots:
                if prots[sub[0]].decay == 'NED':
                    nvals.append(prots[sub[0]].abundance)
                elif prots[sub[0]].decay == 'ED':
                    evals.append(prots[sub[0]].abundance)
            else:
                for p in sub:
                    if p in prots and prots[p].decay == 'NED':
                        nvals.append(prots[p].abundance)
                        break
                    elif p in prots and prots[p].decay == 'ED':
                        evals.append(prots[p].abundance)
                        break
        if len(evals) > 0 and len(nvals) > 0:
            trials += 1
            if np.mean(nvals) >= np.mean(evals):
                success += 1
    print(success, trials, binom_test(success, trials))

def tissue_count2(species, homologs=False):
    header, data = load_ned_data('data/NED_{0}_Abund.txt'.format(species))

    fname = 'data/abundance/human_proteomicsdb_tissue_expression.txt'
    with open(fname) as infile:
        tdata = [line.strip().split('\t') for line in infile]
    tcounts = {line[0]: int(line[-2]) for line in tdata[1:]}

    Prot = namedtuple('Prot', ['tcount', 'decay'])
    if homologs == True:
        core = ix.dbloader.LoadCorum('Human', 'core')
        homs = map_mouse_homologs()
        prots = {homs[line[-2]]: (Prot(tcounts[homs[line[-2]]], line[-3]))
                 for line in data if line[-2] in homs and homs[line[-2]]
                 in tcounts}
    else:
        core = ix.dbloader.LoadCorum(species.title(), 'core')
        prots = {line[-2]: Prot(tcounts[line[-2]], line[-3]) for line in data
                 if line[-2] in tcounts}
    success, trials = 0, 0
    for struc in core.strucs:
        nvals = []
        evals = []
        subunits = core[struc].uniprot
        for sub in subunits:
            # Deals with ambiguous (bracketed) subunits
            if len(sub) == 1 and sub[0] in prots:
                if prots[sub[0]].decay == 'NED':
                    nvals.append(prots[sub[0]].tcount)
                elif prots[sub[0]].decay == 'ED':
                    evals.append(prots[sub[0]].tcount)
            else:
                for p in sub:
                    if p in prots and prots[p].decay == 'NED':
                        nvals.append(prots[p].tcount)
                        break
                    elif p in prots and prots[p].decay == 'ED':
                        evals.append(prots[p].tcount)
                        break
        if len(evals) > 0 and len(nvals) > 0:
            trials += 1
            if np.mean(nvals) >= np.mean(evals):
                success += 1
    print(success, trials, binom_test(success, trials))

def map_mouse_homologs():
    with open('data/uniprot_homologs.txt') as infile:
        infile.readline()
        homologs = {l.split()[0]: l.split()[1] for l in infile}
    return homologs

def main():
    abundance_binomial_test('mouse', True)
    abundance_binomial_test('human')
    # tissue_count2('mouse', True)
    tissue_count2('mouse', True)
    tissue_count2('human', False)


if __name__ == '__main__':
    main()
