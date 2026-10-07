"""Closed, conforming Q9 annular meshes for an entire generated spur gear.

This is a numerical building block for loaded-mesh analysis, not a new rating
method. The bore is fully clamped; no radial cut face or duplicate seam remains.
"""
import math

import numpy as np

from .elasticity import MAX_ELEMENTS
from .engineering import _integer
from .models import finite


def annular_gear_mesh(profile, support_radius_mm, angular_divisions_per_tooth=8,
                      radial_layers=4, patches_by_tooth=()):
    """Return a full ring; patch records are (integer tooth index, patch dict).

    Tooth zero is centered on +Y; indices increase clockwise. Patch breakpoints
    are placed on both flanks of the selected tooth. Geometry is piecewise
    bilinear, with quadratic displacement interpolation, as in the sector mesh.
    """
    divisions=_integer(angular_divisions_per_tooth,'Angular divisions per tooth',4,256)
    layers=_integer(radial_layers,'Radial layers',2,96)
    inner=finite(support_radius_mm,'Clamped bore radius mm',.001,50000)
    if inner>=profile.rf-.1*profile.m:
        raise ValueError('Support radius must leave at least 0.1 module beneath the generated root')
    pitch=2*math.pi/profile.z;start=-pitch/2;end=2*math.pi-pitch/2
    anchors=[start,end]
    for tooth in range(profile.z):
        anchors.extend(tooth*pitch+angle for angle in
                       (-pitch/2,-profile.phif,-profile.phij,-profile.phia,0,profile.phia,profile.phij,profile.phif))
    requests=list(patches_by_tooth)
    if len(requests)>128:raise ValueError('Use at most 128 tooth/patch anchor requests')
    for tooth,patch in requests:
        index=_integer(tooth,'Loaded tooth index',-profile.z,profile.z-1)%profile.z
        lo=finite(patch['minimum_angle_rad'],'Patch minimum angle',0,pitch/2)
        hi=finite(patch['maximum_angle_rad'],'Patch maximum angle',0,pitch/2)
        if lo>=hi:raise ValueError('Patch angular interval must increase')
        anchors.extend(index*pitch+sign*value for value in (lo,hi) for sign in (-1,1))
    anchors=np.unique(np.round(anchors,14));angles=[];step=pitch/divisions
    for a,b in zip(anchors,anchors[1:]):
        # Prevent roundoff near an integral subdivision count from giving
        # rotationally identical teeth different element counts.
        angles.extend(np.linspace(a,b,max(1,math.ceil((b-a)/step-1e-10))+1)[:-1])
    angles=np.array([*angles,anchors[-1]]);columns=len(angles)-1
    if columns*layers>MAX_ELEMENTS or 2*columns*(2*layers+1)>90000:
        raise ValueError('Whole-gear mesh exceeds the 40,000-cell / 90,000-node limit')
    local=(angles[:-1]+pitch/2)%pitch-pitch/2
    outer=np.array([profile.radius_at_angle(a) for a in local])
    radial=1-(1-np.linspace(0,1,layers+1))**1.5
    radii=inner+radial[:,None]*(outer[None,:]-inner)
    nodes=np.stack((radii*np.sin(angles[:-1]),radii*np.cos(angles[:-1])),axis=-1).reshape(-1,2)
    column=np.arange(columns);following=(column+1)%columns
    lower=(np.arange(layers)[:,None]*columns+column).ravel()
    lower_next=(np.arange(layers)[:,None]*columns+following).ravel()
    cells=np.column_stack((lower,lower_next,lower_next+columns,lower+columns))
    coordinates=nodes.tolist();midpoints={};quadratic=[]
    for cell in cells:
        middle=[]
        for a,b in zip(cell,np.roll(cell,-1)):
            edge=tuple(sorted((int(a),int(b))))
            if edge not in midpoints:
                midpoints[edge]=len(coordinates);coordinates.append(((nodes[a]+nodes[b])/2).tolist())
            middle.append(midpoints[edge])
        center=len(coordinates);coordinates.append(nodes[cell].mean(axis=0).tolist())
        quadratic.append([*cell,*middle,center])
    outer_nodes=np.r_[layers*columns+column,layers*columns]
    outer_midpoints=[midpoints[tuple(sorted((int(a),int(b))))] for a,b in zip(outer_nodes,outer_nodes[1:])]
    fixed_nodes=[*column,*(midpoints[tuple(sorted((int(a),int(b))))] for a,b in zip(column,following))]
    mids=(angles[:-1]+angles[1:])/2;tooth_indices=np.floor((mids+pitch/2)/pitch).astype(int)
    local_mids=mids-tooth_indices*pitch
    root_columns=np.flatnonzero((abs(local_mids)>profile.phij-1e-12)&(abs(local_mids)<profile.phif+1e-12))
    return dict(nodes=np.array(coordinates),elements=np.array(quadratic),angles=angles,
                outer_nodes=outer_nodes,outer_midpoints=outer_midpoints,
                fixed_dofs=(2*np.array(fixed_nodes)[:,None]+[0,1]).ravel(),
                root_columns=root_columns,root_elements=(layers-1)*columns+root_columns,
                root_tooth_indices=tooth_indices[root_columns],sector_teeth=profile.z,
                radial_layers=layers,periodic=True)
