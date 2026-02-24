import numpy as np
from deap import base, creator, tools, algorithms
import random
import logging
from .backtester import Backtester

class ParameterOptimizer:
    def __init__(self, strategy_class, data, param_ranges):
        """
        param_ranges: dict with parameter names and (min, max, step) tuples
        Example: {'fast_ema': (5, 20, 1), 'slow_ema': (20, 50, 1)}
        """
        self.strategy_class = strategy_class
        self.data = data
        self.param_ranges = param_ranges
        self.param_names = list(param_ranges.keys())
        
    def evaluate_params(self, individual):
        """Fitness function for genetic algorithm"""
        params = {name: individual[i] for i, name in enumerate(self.param_names)}
        
        # Add fixed parameters
        if 'rsi_period' not in params:
            params['rsi_period'] = 14
        if 'atr_period' not in params:
            params['atr_period'] = 14
        if 'rsi_overbought' not in params:
            params['rsi_overbought'] = 70
        if 'rsi_oversold' not in params:
            params['rsi_oversold'] = 30
        if 'atr_multiplier' not in params:
            params['atr_multiplier'] = 1.5
        if 'take_profit_pips' not in params:
            params['take_profit_pips'] = 50
        if 'stop_loss_pips' not in params:
            params['stop_loss_pips'] = 30
        
        try:
            strategy = self.strategy_class(params)
            backtester = Backtester(strategy)
            results = backtester.run(self.data)
            
            # Fitness: combination of profit and risk-adjusted return
            if results['total_trades'] < 10:
                return (-1000,)  # Penalize strategies with too few trades
            
            # Multi-objective: maximize profit factor and minimize drawdown
            fitness = (
                results['profit_factor'] * 
                (1 - abs(results['max_drawdown'])) * 
                results['total_profit']
            )
            
            return (fitness,)
        except Exception as e:
            logging.error(f"Error evaluating params: {e}")
            return (-1000,)
    
    def optimize_genetic(self, population_size=50, generations=20):
        """Use genetic algorithm to find optimal parameters"""
        
        # Create fitness and individual classes
        creator.create("FitnessMax", base.Fitness, weights=(1.0,))
        creator.create("Individual", list, fitness=creator.FitnessMax)
        
        toolbox = base.Toolbox()
        
        # Register parameter generators
        for i, (param_name, (min_val, max_val, step)) in enumerate(self.param_ranges.items()):
            if isinstance(min_val, int):
                toolbox.register(f"attr_{i}", random.randint, min_val, max_val)
            else:
                toolbox.register(f"attr_{i}", random.uniform, min_val, max_val)
        
        # Create individual and population
        toolbox.register("individual", tools.initCycle, creator.Individual,
                        [getattr(toolbox, f"attr_{i}") for i in range(len(self.param_names))],
                        n=1)
        toolbox.register("population", tools.initRepeat, list, toolbox.individual)
        
        # Register genetic operators
        toolbox.register("evaluate", self.evaluate_params)
        toolbox.register("mate", tools.cxTwoPoint)
        toolbox.register("mutate", tools.mutGaussian, mu=0, sigma=1, indpb=0.2)
        toolbox.register("select", tools.selTournament, tournsize=3)
        
        # Run optimization
        pop = toolbox.population(n=population_size)
        hof = tools.HallOfFame(1)
        
        stats = tools.Statistics(lambda ind: ind.fitness.values)
        stats.register("avg", np.mean)
        stats.register("max", np.max)
        
        logging.info("Starting genetic algorithm optimization...")
        pop, logbook = algorithms.eaSimple(pop, toolbox, cxpb=0.7, mutpb=0.2,
                                           ngen=generations, stats=stats,
                                           halloffame=hof, verbose=True)
        
        # Get best parameters
        best_individual = hof[0]
        best_params = {name: best_individual[i] for i, name in enumerate(self.param_names)}
        
        logging.info(f"Best parameters found: {best_params}")
        
        return best_params, logbook
    
    def grid_search(self):
        """Exhaustive grid search (use for small parameter spaces)"""
        best_fitness = -float('inf')
        best_params = None
        
        # Generate all combinations
        param_values = []
        for param_name, (min_val, max_val, step) in self.param_ranges.items():
            if isinstance(min_val, int):
                values = list(range(min_val, max_val + 1, step))
            else:
                values = list(np.arange(min_val, max_val + step, step))
            param_values.append(values)
        
        # Test all combinations
        import itertools
        total_combinations = np.prod([len(v) for v in param_values])
        logging.info(f"Testing {total_combinations} parameter combinations...")
        
        for i, combination in enumerate(itertools.product(*param_values)):
            params = dict(zip(self.param_names, combination))
            fitness = self.evaluate_params(list(combination))[0]
            
            if fitness > best_fitness:
                best_fitness = fitness
                best_params = params
            
            if (i + 1) % 100 == 0:
                logging.info(f"Tested {i + 1}/{total_combinations} combinations")
        
        logging.info(f"Best parameters found: {best_params} with fitness: {best_fitness}")
        return best_params
