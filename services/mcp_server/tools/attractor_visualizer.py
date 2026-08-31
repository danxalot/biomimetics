import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import io
import base64

class AttractorVisualizer:
    """
    Visualizes High-Dimensional Holographic Memory in 3D Space.
    
    Principles:
    1. Random Projection (Johnson-Lindenstrauss): 
       We project 10,000D -> 3D using a fixed random matrix. 
       This preserves relative distances and geometry surprisingly well.
    2. Trajectory: Plots the path of the conversation state over time.
    3. Momentum: Visualizes the velocity vectors.
    4. Attractors: Shows fixed points (like 'Start' or specific memories).
    """
    
    def __init__(self, input_dim=10000, output_dim=3, seed=42):
        self.input_dim = input_dim
        self.output_dim = output_dim
        
        # Initialize fixed projection matrix (for consistent visualization across calls)
        np.random.seed(seed)
        # Gaussian Randomized Matrix
        self.projection_matrix = np.random.randn(input_dim, output_dim) / np.sqrt(output_dim)

    def project(self, vector):
        """Projects a vector (D,) to (3,)."""
        return np.dot(vector, self.projection_matrix)

    def generate_plot(self, history, title="Holographic Memory State Space"):
        """
        Generates a 3D plot of the conversation history.
        
        Args:
            history: List of turn dicts (must contain 'vector').
            
        Returns:
            Path to saved image (or base64 string).
        """
        if not history:
            return None
            
        fig = plt.figure(figsize=(10, 8))
        ax = fig.add_subplot(111, projection='3d')
        
        dims = {'x': [], 'y': [], 'z': []}
        
        # 1. Project Points
        vectors_3d = []
        for item in history:
            if "vector" in item:
                v_3d = self.project(item["vector"])
                vectors_3d.append(v_3d)
                dims['x'].append(v_3d[0])
                dims['y'].append(v_3d[1])
                dims['z'].append(v_3d[2])
                
        if not vectors_3d:
            return None
            
        xs, ys, zs = dims['x'], dims['y'], dims['z']
        
        # 2. Plot Trajectory Line
        ax.plot(xs, ys, zs, color='cyan', alpha=0.5, label='Context Trajectory')
        
        # 3. Plot Points (Turns)
        # Color gradient by time
        colors = plt.cm.viridis(np.linspace(0, 1, len(xs)))
        ax.scatter(xs, ys, zs, c=colors, s=50, edgecolors='w', alpha=0.8)
        
        # 4. Plot Momentum Arrows
        # We draw an arrow from t to t+1
        for i in range(len(vectors_3d) - 1):
            start = vectors_3d[i]
            end = vectors_3d[i+1]
            # Direction
            uvw = end - start
            # Plot only if movement is significant
            if np.linalg.norm(uvw) > 0.1:
                ax.quiver(start[0], start[1], start[2], 
                         uvw[0], uvw[1], uvw[2], 
                         length=1.0, normalize=False, color='magenta', alpha=0.3, arrow_length_ratio=0.3)

        # Labels
        ax.set_title(title)
        ax.set_xlabel('Projected Dim 1')
        ax.set_ylabel('Projected Dim 2')
        ax.set_zlabel('Projected Dim 3')
        
        # Legend
        ax.legend()
        
        # Save to buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100)
        buf.seek(0)
        plt.close(fig)
        
        return buf.getvalue()
    
    def save_plot_to_file(self, history, filepath="/app/shared_storage/memory/visualization.png"):
        """Saves the 3D plot to a file."""
        import os
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        img_data = self.generate_plot(history)
        if img_data:
            with open(filepath, "wb") as f:
                f.write(img_data)
            return filepath
        return None
