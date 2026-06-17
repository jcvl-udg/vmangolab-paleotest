import xsimlab as xs

from ..processes import (
    topology,
    geometry,
    environment,
    phenology,
    appearance,
    growth,
    arch_dev_veg_within,
    arch_dev_veg_between,
    arch_dev_rep,
    arch_dev_mix,
    arch_dev,
    light_interception,
    photosynthesis,
    carbon_flow_coef,
    carbon_reserve,
    carbon_demand,
    carbon_allocation,
    fruit_composition,
    fruit_quality,
    harvest
)

vmango = xs.Model({
    'environment': environment.Environment,
    'phenology': phenology.Phenology,
    'topology': topology.Topology,
    'geometry': geometry.Geometry,
    'appearance': appearance.Appearance,
    'growth': growth.Growth,
    'arch_dev_veg_within': arch_dev_veg_within.ArchDevVegWithin,
    'arch_dev_veg_between': arch_dev_veg_between.ArchDevVegBetween,
    'arch_dev_rep': arch_dev_rep.ArchDevRep,
    'arch_dev_mix': arch_dev_mix.ArchDevMix,
    'arch_dev': arch_dev.ArchDevStochastic,
    'light_interception': light_interception.LightInterception,
    'photosynthesis': photosynthesis.Photosythesis,
    'carbon_flow_coef': carbon_flow_coef.CarbonFlowCoef,
    'carbon_reserve': carbon_reserve.CarbonReserve,
    'carbon_demand': carbon_demand.CarbonDemand,
    'carbon_allocation': carbon_allocation.CarbonAllocation,
    'fruit_composition': fruit_composition.FruitComposition,
    'fruit_quality': fruit_quality.FruitQuality,
    'harvest': harvest.Harvest
})


arch_dev_model = xs.Model({
    'topology': topology.Topology,
    'arch_dev_veg_within': arch_dev_veg_within.ArchDevVegWithin,
    'arch_dev_veg_between': arch_dev_veg_between.ArchDevVegBetween,
    'arch_dev_rep': arch_dev_rep.ArchDevRep,
    'arch_dev_mix': arch_dev_mix.ArchDevMix,
    'arch_dev': arch_dev.ArchDevStochastic
})

fruit_model = xs.Model({
    'environment': environment.Environment,
    'phenology': phenology.Phenology,
    'topology': topology.Topology,
    'geometry': geometry.Geometry,
    'appearance': appearance.Appearance,
    'growth': growth.Growth,
    'arch_dev': arch_dev.ArchDev,
    'light_interception': light_interception.LightInterception,
    'photosynthesis': photosynthesis.Photosythesis,
    'carbon_flow_coef': carbon_flow_coef.CarbonFlowCoef,
    'carbon_reserve': carbon_reserve.CarbonReserve,
    'carbon_demand': carbon_demand.CarbonDemand,
    'carbon_allocation': carbon_allocation.CarbonAllocation,
    'fruit_composition': fruit_composition.FruitComposition,
    'fruit_quality': fruit_quality.FruitQuality,
    'harvest': harvest.Harvest
})

longnames = {
    'environment': 'Environment',
    'phenology': 'Organ Phenology',
    'topology': 'Topological Growth',
    'geometry': 'Geometrical Representation',
    'appearance': 'Organ Initiation',
    'growth': 'Organ Growth',
    'arch_dev_veg_within': 'Vegetative Devel Within Cycle',
    'arch_dev_veg_between': 'Vegetative Devel Between Cycle',
    'arch_dev_rep': 'Reproductive Devel',
    'arch_dev_mix': 'Mixed Inflo Devel',
    'arch_dev': 'Integrative Devel',
    'light_interception': 'Light Interception',
    'photosynthesis': 'Photosynthesis',
    'carbon_flow_coef': 'Carbon Flow Coef',
    'carbon_reserve': 'Carbon Reserve',
    'carbon_demand': 'Carbon Demand',
    'carbon_allocation': 'Carbon Allocation',
    'fruit_composition': 'Fruit Composition',
    'fruit_quality': 'Fruit Quality',
    'harvest': 'Fruit Harvest'
}


def longname_model(model):
    process_names = list(model.all_vars_dict.keys())
    processes = {}
    for p in process_names:
        processes[longnames[p]] = model[p].__class__
    return xs.Model(processes)
