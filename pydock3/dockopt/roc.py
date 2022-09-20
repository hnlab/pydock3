from dataclasses import dataclass
import math

import numpy as np
from pytoc import TOC
from scipy import interpolate
from matplotlib import pyplot as plt


@dataclass
class Point:
    x: float
    y: float


class ROC(object):
    def __init__(self, booleans, indices):
        #
        self.booleans = booleans
        self.indices = indices

        # get TOC points
        booleans_array = np.array(booleans)
        indices_array = np.array(indices)
        thresholds_array = np.unique(indices_array)
        toc = TOC(booleans_array, indices_array, thresholds_array)
        toc_x_coords = np.array(toc.TOCX[0], dtype=float)
        toc_y_coords = np.array(toc.TOCY[0], dtype=float)
        toc_x_coords, toc_y_coords = zip(*sorted(zip(toc_x_coords, toc_y_coords)))
        toc_x_coords = np.array(toc_x_coords)
        toc_y_coords = np.array(toc_y_coords)

        # get ROC points
        roc_x_coords = toc_x_coords - toc_y_coords  # unshear the TOC
        roc_y_coords = toc_y_coords
        mask = np.zeros(len(roc_x_coords), dtype=bool)
        roc_points_x_unique = list(np.unique(roc_x_coords))
        for x_unique in roc_points_x_unique:
            indices = [index for index, x in enumerate(roc_x_coords) if x == x_unique]
            # set mask element to True only if index corresponds to max y for given x
            max_index = indices[0]
            for index in indices:
                if toc_y_coords[index] > toc_y_coords[max_index]:
                    max_index = index
            mask[max_index] = True
        roc_x_coords = roc_x_coords[mask] / self.num_decoys
        roc_y_coords = roc_y_coords[mask] / self.num_actives

        #
        self.points = [Point(roc_x_coords[i], roc_y_coords[i]) for i in range(len(roc_x_coords))]

        #
        roc_x_coords = [point.x for point in self.points]
        roc_y_coords = [point.y for point in self.points]
        self.f = lambda w: float(interpolate.interp1d(roc_x_coords, roc_y_coords, kind='previous')(w))

        #
        self.alpha = float(1 / (self.num_decoys * np.e))

        #
        self.enrichment_score = self._get_enrichment_score()

    @property
    def num_actives(self):
        return len([b for b in self.booleans if b])

    @property
    def num_decoys(self):
        return len([b for b in self.booleans if not b])
    
    def _get_enrichment_score(self):
        return (self._get_literal_area_under_roc_curve_with_log_scaled_x_axis() - (1 - self.alpha)) / (-np.log(self.alpha) - (1 - self.alpha))

    def _get_literal_area_under_roc_curve_with_log_scaled_x_axis(self):
        weights = [np.log(1 / (self.alpha * self.num_decoys))] + [np.log((i+1)/i) for i in range(1, self.num_decoys)]
        y_values_of_interdecoy_intervals = [self.f(self.alpha)] + [self.f(float(i/self.num_decoys)) for i in range(1, self.num_decoys)]  # leave out last point (1,1) since we want n intervals
        return np.dot(weights, y_values_of_interdecoy_intervals)

    def plot(self, save_path):
        # make plot of ROC curve of actives vs. decoys with log-scaled x-axis
        fig, ax = plt.subplots()
        fig.set_size_inches(8.0, 8.0)
        roc_x_coords = [point.x for point in self.points]
        roc_y_coords = [point.y for point in self.points]
        ax.step(roc_x_coords, roc_y_coords, where='post', label=f"enrichment_score: {round(self.enrichment_score, 2)}")
        ax.legend()

        # draw curve of random classifier for reference
        ax.semilogx([float(i / 100) for i in range(0, 101)], [float(i / 100) for i in range(0, 101)], "--", linewidth=1, color='Black')

        # set axis labels
        ax.set_xlabel('top fraction of decoys')
        ax.set_ylabel('top fraction of actives')

        # set log scale x-axis
        ax.set_xscale('log')

        # set plot axis limits
        ax.set_xlim(left=self.alpha, right=1.0)
        ax.set_ylim(bottom=0.0, top=1.0)

        # set axis ticks
        order_of_magnitude = math.floor(math.log(self.num_decoys, 10))
        ax.set_xticks([self.alpha] + [float(10 ** x) for x in range(-order_of_magnitude, 1, 1)])
        ax.set_yticks([float(j / 10) for j in range(0, 11)])

        # set title and include alpha to account for inconsistent inclusion of alpha in xticks
        ax.set_title(f"Log ROC (num_decoys={self.num_decoys}, num_actives={self.num_actives}, cutoff={np.format_float_scientific(self.alpha, precision=3)})")

        # save image and close
        plt.tight_layout()
        plt.savefig(save_path)
        plt.close(fig)
