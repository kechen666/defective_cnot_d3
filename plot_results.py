"""General research figures; every plotted estimate retains its count and CI."""
import argparse
import json
from pathlib import Path
import patches
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np


def save_figure(fig, stem):
    for extension in ('png','svg'):
        fig.savefig(stem.with_suffix('.'+extension),dpi=200,facecolor='white')
    plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,default=patches.HERE/'results')
    args=parser.parse_args()
    folder=args.results/'figures'
    folder.mkdir(parents=True,exist_ok=True)
    summary=json.loads((args.results/'summary.json').read_text(encoding='utf-8'))
    colors={'healthy':'#0072B2','defective':'#D55E00'}
    with plt.rc_context({'font.size':10,'svg.fonttype':'none','axes.spines.top':False,
                         'axes.spines.right':False,'figure.facecolor':'white'}):
        fig,axes=plt.subplots(1,2,figsize=(10,4.4),layout='constrained',sharey=True)
        for ax,basis in zip(axes,'XZ'):
            for case,marker in [('healthy','o'),('defective','s')]:
                rows=sorted((r for r in summary['statistics'] if r['case']==case and r['basis']==basis),key=lambda r:r['p'])
                x=np.array([r['p'] for r in rows])
                y=np.array([r['decoded_failure_rate'] for r in rows])
                low,high=np.array([r['decoded_wilson95'] for r in rows]).T
                ax.errorbar(x,y,yerr=np.array([y-low,high-y]),fmt=marker,markersize=6,
                            capsize=4,color=colors[case],label=f'{case}: decoded')
                ax.plot(x,[r['raw_failure_rate'] for r in rows],marker=marker,linestyle='none',
                        markersize=6,fillstyle='none',color=colors[case],label=f'{case}: raw')
            ax.set(xscale='log',xlabel='Physical noise probability p (log scale)',
                   title=f'{basis} logical readout',ylim=(0,0.8))
            ax.set_xticks([1e-4,1e-3,3e-3],labels=[r'$10^{-4}$',r'$10^{-3}$',r'$3\times10^{-3}$'])
            ax.grid(axis='y',color='#dddddd')
        axes[0].set_ylabel('Any logical failure / complete experiment')
        axes[1].legend(loc='upper left',fontsize=8)
        fig.suptitle(f'Nominal d=3, 30 syndrome rounds; {summary["config"]["shots_per_group"]:,} shots / point\nDecoded: 95% Wilson intervals; raw: open markers; no fitted curves',fontsize=11)
        save_figure(fig,folder/'logical_error_rates')
        ps=patches.build_patches(True)
        fig,axes=plt.subplots(1,3,figsize=(13.5,5.6))
        fig.subplots_adjust(left=0.06,right=0.99,top=0.85,bottom=0.19,wspace=0.13)
        for ax,names,title in zip(axes,[('C','A','T'),('CA','T'),('C','AT')],
                                 ['Separate patches / split','ZZ merge (C+A)','XX merge (A+T)']):
            for name in names:
                p=ps[name]
                for c in p.checks:
                    color='#0072B2' if c.basis=='X' else '#A64A00'
                    for q in c.data:
                        ax.plot([q[0],c.ancilla[0]],[q[1],c.ancilla[1]],
                                color=color,lw=0.65,ls='--' if c.gauge else '-',zorder=1)
                    ax.scatter(*c.ancilla,c=color,marker='s' if c.basis=='X' else '^',s=22,zorder=2)
                ax.scatter(*np.array(p.data).T,c='#222222',s=19,zorder=3)
                center=np.mean(p.data,axis=0)
                ax.text(center[0]+0.6,center[1]+0.5,name,fontweight='bold',
                        bbox={'facecolor':'white','edgecolor':'none','alpha':0.85})
            ax.scatter(*patches.DEAD,c='#B00020',s=110,marker='x',linewidth=2.5,zorder=4)
            ax.set(title=title,xlim=(-1,15),ylim=(-1,15),xlabel='Hardware x',aspect='equal')
            ax.set_xticks([1,3,5,7,9,11,13]); ax.set_yticks([1,3,5,7,9,11,13])
        axes[0].set_ylabel('Hardware y')
        handles=[Line2D([],[],color='#222222',marker='o',ls='',label='healthy data'),
                 Line2D([],[],color='#0072B2',marker='s',ls='',label='X check ancilla'),
                 Line2D([],[],color='#A64A00',marker='^',ls='',label='Z check ancilla'),
                 Line2D([],[],color='#555555',ls='--',label='gauge support'),
                 Line2D([],[],color='#B00020',marker='x',ls='',label='dead data (3,11)')]
        fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(0.5,0.01),ncol=5,fontsize=9)
        fig.suptitle('Fixed d=3 windows, center data defect; X/Z gauges alternate in time',fontsize=12)
        save_figure(fig,folder/'patch_layouts')
    manifest={'audience':'provisional general research demo; no journal target',
              'source_data':'../summary.json and ../statistics.csv; patches from pinned SnL',
              'estimate':'per-shot any-observable logical failure probability',
              'uncertainty':'95% Wilson binomial interval, independent complete-experiment shots',
              'transformations':'counts / shots only; logarithmic x axis, linear y including zero; no exclusions or fits',
              'formats':['SVG, editable labels','PNG, 200 dpi'],
              'dimensions_inches':{'logical_error_rates':[10,4.4],'patch_layouts':[13.5,5.6]},
              'matplotlib_version':matplotlib.__version__,
              'alt_text':{'logical_error_rates':'Two panels for X and Z readout. Filled markers with confidence intervals show decoded any-logical-error rates; open markers show raw rates. Healthy circles and defective squares are distinguished by shape and color. All twelve measured groups are shown.',
                          'patch_layouts':'Three panels show separate C/A/T patches, merged C+A with T, and C with merged A+T. Data are dots, X checks squares, Z checks triangles. The dead control-center data site (3,11) is a red cross, and gauge support uses dashed lines.'}}
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(f'Figures written to {folder}')


if __name__=='__main__':
    main()
