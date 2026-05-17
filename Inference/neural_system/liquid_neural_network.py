import numpy as np
# import scipy.linalg # Not needed for basic step
from typing import Tuple, List, Optional, Callable

class LiquidNeuralNetwork:
    """
    Liquid Time-Constant (LTC) Network.
    
    A biologically inspired continuous-time neural network.
    Based on 'Neural Circuit Policies' (Hasani et al.).
    
    Equation:
    dx(t)/dt = - [x(t) / tau] + f(x, I, t)
    
    Where:
    - tau: Liquid time-constant (state dependent!)
    - f: Nonlinear interaction term (synapses)
    - I: Input
    
    Why for ARCA:
    1. Continuous Time: Matches the Physics Engines (Kuramoto/Quaternion).
    2. Adaptive: 'tau' changes based on input, allowing fast/slow thinking.
    3. Sparse: Modeling sparse neural biological circuits is cheap on OCI.
    """

    def __init__(self, n_neurons: int, n_inputs: int, dt: float = 0.01):
        self.N = n_neurons
        self.input_dim = n_inputs
        self.dt = dt
        
        # State vector x(t)
        self.state = np.zeros(self.N, dtype=np.float32)
        
        # --- Parameters (Random initialization for now) ---
        # Time constants base
        self.tau_base = np.random.uniform(0.1, 1.0, self.N).astype(np.float32)
        
        # Weights
        # W_in: Input -> Internal
        self.W_in = np.random.randn(self.N, self.input_dim) * 0.1
        # W_rec: Internal -> Internal (Recurrent)
        self.W_rec = np.random.randn(self.N, self.N) * 0.1
        
        # Bias
        self.bias = np.zeros(self.N, dtype=np.float32)
        
        # Nonlinearity (Sigmoid/Tanh)
        self.act = np.tanh

    def step(self, input_vec: np.ndarray) -> np.ndarray:
        """
        Euler integration step.
        """
        x = self.state
        I = input_vec
        
        # Compute Synaptic Inputs
        # S(t) = W_rec * act(x) + W_in * I + bias
        synaptic_input = (self.W_rec @ self.act(x)) + (self.W_in @ I) + self.bias
        
        # Compute Liquid Time Constant
        # tau(x) = tau_base / (1 + |synaptic_input|)
        # This makes the neuron react faster (smaller tau) when stimulated heavily
        tau_liquid = self.tau_base / (1.0 + np.abs(synaptic_input))
        
        # ODE: dx/dt = -(x - synaptic_input) / tau
        # Wait, standard Leaky Integrator is: dx/dt = -x/tau + I
        # LTC formulation is slightly richer: 
        # dx/dt = -[1/tau + nonlinearity] * x + nonlinearity
        
        # Simplified LTC for stability in Python proto:
        # dx = dt * (-x + synaptic_input) / tau_liquid
        
        dx = self.dt * (-x + synaptic_input) / tau_liquid
        
        # Update state
        self.state = x + dx
        
        return self.state

    def reset_state(self):
        self.state = np.zeros(self.N, dtype=np.float32)
