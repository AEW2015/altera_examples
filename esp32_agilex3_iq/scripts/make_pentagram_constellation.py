#!/usr/bin/env python3
"""Create a pentagram/circle SVG and its explicit transition graph. No hardware."""
import json,math
from pathlib import Path
from common import ROOT

def generate():
    output=ROOT/'examples/svg_constellations';output.mkdir(parents=True,exist_ok=True)
    points=[(math.cos(-math.pi/2+i*2*math.pi/5),math.sin(-math.pi/2+i*2*math.pi/5)) for i in range(5)]
    fmt=lambda value:f'{value:.12f}'
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="640" height="640" viewBox="-1.15 -1.15 2.3 2.3" role="img" aria-labelledby="title description">',
         '<title id="title">Pentagram inscribed in a circle</title>',
         '<desc id="description">Five constellation points lie on the circle. Straight star edges and circular arcs define transitions. Crossings are not nodes.</desc>',
         '<rect x="-1.15" y="-1.15" width="2.3" height="2.3" fill="#ffffff"/>',
         '<g id="circle-edges" fill="none" stroke="#0891b2" stroke-width="0.012" stroke-linecap="round">']
    edges=[]
    for i,(x,y) in enumerate(points):
        j=(i+1)%5;u,v=points[j]
        svg.append(f'<path id="circle-{i}-{j}" data-from="p{i}" data-to="p{j}" data-kind="circle" d="M {fmt(x)} {fmt(y)} A 1 1 0 0 1 {fmt(u)} {fmt(v)}"/>')
        edges.append(dict(id=f'circle-{i}-{j}',source=f'p{i}',target=f'p{j}',kind='circle',bidirectional=True))
    svg+=['</g>','<g id="star-edges" fill="none" stroke="#7c3aed" stroke-width="0.012" stroke-linecap="round" stroke-linejoin="round">']
    for i,(x,y) in enumerate(points):
        j=(i+2)%5;u,v=points[j]
        svg.append(f'<line id="star-{i}-{j}" data-from="p{i}" data-to="p{j}" data-kind="star" x1="{fmt(x)}" y1="{fmt(y)}" x2="{fmt(u)}" y2="{fmt(v)}"/>')
        edges.append(dict(id=f'star-{i}-{j}',source=f'p{i}',target=f'p{j}',kind='star',bidirectional=True))
    svg+=['</g>','<g id="constellation" fill="#172554" stroke="#ffffff" stroke-width="0.004">']
    for i,(x,y) in enumerate(points):svg.append(f'<circle id="p{i}" data-node="true" cx="{fmt(x)}" cy="{fmt(y)}" r="0.016"/>')
    svg+=['</g>','</svg>']
    target=output/'pentagram_circle.svg';target.write_text('\n'.join(svg)+'\n')
    transitions=[]
    # Direction labels are relative to clockwise SVG node numbering. Complement
    # label pairs have endpoints separated by144deg, not a coding-gain claim.
    for i in range(5):
        for bits,delta,kind in [('00',1,'circle'),('01',2,'star'),('10',-1,'circle'),('11',-2,'star')]:
            transitions.append(dict(source=f'p{i}',target=f'p{(i+delta)%5}',edge_bits=bits,kind=kind))
    graph=dict(schema='svg-edge-constellation-graph-v1',svg=target.name,implemented_in_fpga=False,rf_tested=False,
               origin=[0,0],circle_radius=1,svg_y_down=True,crossings_are_nodes=False,
               nodes=[dict(id=f'p{i}',svg_x=x,svg_y=y,i=x,q=-y) for i,(x,y) in enumerate(points)],edges=edges,directed_transitions=transitions,
               constraint_only=dict(input_bits_per_transition=2,allowed_out_degree=4,forbidden='self transitions',guaranteed_single_symbol_correction=False),
               proposed_fec=dict(encoder='K7 rate-1/2 (171,133 octal)',coded_pair_selects='edge_bits',emitted_symbol='destination node I/Q',joint_decoder_states=320,payload_bits_per_symbol_before_termination=1,measured_coding_gain_db=None))
    (output/'pentagram_circle.graph.json').write_text(json.dumps(graph,indent=2)+'\n')
    # Geometry and graph contract checks, including all tip/circle contacts.
    assert all(abs(x*x+y*y-1)<1e-12 for x,y in points)
    pairs={frozenset((e['source'],e['target'])) for e in edges}
    assert len(pairs)==10 and len(transitions)==20
    for i in range(5):
        row=[e for e in transitions if e['source']==f'p{i}']
        assert len({e['target'] for e in row})==4 and {e['edge_bits'] for e in row}=={'00','01','10','11'}
    return target
if __name__=='__main__':print(generate())
