# models/paleo_models.py - COMPLETELY SEPARATE FILE
import xsimlab as xs

# Import ALL original processes
from ..processes import (
    topology,
    geometry
)

# Import paleo environment
from ..paleo_processes import ( 
        paleo_environment,
        paleo_phenology,
        paleo_appearance,
        paleo_growth,
        paleo_light_interception,
        paleo_photosynthesis,
        paleo_carbon_flow_coef,
        paleo_carbon_reserve,
        paleo_carbon_demand,
        paleo_carbon_allocation,
        paleo_harvest,
        paleo_arch_dev_veg_within,
        paleo_arch_dev_veg_between,
        paleo_arch_dev_rep,
        paleo_arch_dev_mix,
        paleo_arch_dev
)

# Minimal viable paleo model - includes ALL required dependencies
paleo_minimal = xs.Model({
    'environment': paleo_environment.Environment,  # Only change!
    'phenology': paleo_phenology.Phenology,
    'topology': topology.Topology,
    'geometry': geometry.Geometry,
    'appearance': paleo_appearance.Appearance,
    'growth': paleo_growth.Growth,
    'arch_dev_veg_within': paleo_arch_dev_veg_within.ArchDevVegWithin,
    'arch_dev_veg_between': paleo_arch_dev_veg_between.ArchDevVegBetween,
    'arch_dev_rep': paleo_arch_dev_rep.ArchDevRep,
    'arch_dev_mix': paleo_arch_dev_mix.ArchDevMix,
    'arch_dev': paleo_arch_dev.ArchDevStochastic,
    'light_interception': paleo_light_interception.LightInterception,
    'photosynthesis': paleo_photosynthesis.Photosythesis,
    'carbon_flow_coef': paleo_carbon_flow_coef.CarbonFlowCoef,
    'carbon_reserve': paleo_carbon_reserve.CarbonReserve,
    'carbon_demand': paleo_carbon_demand.CarbonDemand,
    'carbon_allocation': paleo_carbon_allocation.CarbonAllocation,
    'harvest': paleo_harvest.Harvest
})