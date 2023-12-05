import os
import warnings

import nibabel as nib
import nilearn as nil
import numpy as np
import pandas as pd
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.model_selection import train_test_split

from exareme2.services import imaging_utilities as utils


# Define a function to load and process images with dynamic sizes
def load_and_process_images(folder, target_size):
    # Initialize empty lists for images and labels
    images = []
    labels = []

    # Loop through subfolders in the root directory
    for folder_name in os.listdir(folder):
        folder_path = os.path.join(folder, folder_name)
        if os.path.isdir(folder_path):
            label = folder_name  # Use folder name as the label

            # Loop through image files in each subfolder
            for filename in os.listdir(folder_path):
                if filename.endswith(
                    (".jpg", ".png", ".jpeg")
                ):  # Filter for specific image file extensions
                    file_path = os.path.join(folder_path, filename)
                    try:
                        img = Image.open(file_path)
                        img = img.convert("L")  # Convert to grayscale
                        img = np.array(img)  # Convert image to NumPy array
                        images.append(img)
                        # raise ValueError(images)
                        labels.append(label)
                    except Exception as e:
                        print(f"Error processing {file_path}: {str(e)}")

    return images, labels


class LRImagingLocal:
    def get_parameters(self, config):  # type: ignore
        return utils.get_model_parameters(model)

    def fit(self, parameters, config=None):  # type: ignore
        utils.set_model_params(model, parameters)
        # Ignore convergence failure due to low local epochs
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(X_train, y_train)
        print(f"Training finished for round")  # {config['server_round']}")
        return utils.get_model_parameters(model), len(X_train), {}

    def evaluate(self, parameters, round_num):  # type: ignore
        utils.set_model_params(model, parameters)
        loss = log_loss(y_test, model.predict_proba(X_test))
        accuracy = model.score(X_test, y_test)
        if round_num > 0:
            round_num -= 1
        return loss, len(X_test), {"accuracy": accuracy}, round_num


if __name__ == "__main__":

    # Define the common target size
    target_size = (28, 28)

    # Specify the paths to training and testing image folders
    images_folder = "exareme2/imaging_data/MNIST/training"
    # raise ValueError(images)

    # Load and process both training and testing images
    images, labels = load_and_process_images(images_folder, target_size)

    # Check if images were loaded successfully
    if not images:
        print("No training images were loaded. Check the folder path and image files.")
        exit()

    # Convert images to NumPy arrays
    images = np.array(images)

    data = images.reshape(images.shape[0], -1)
    labels_ds = np.array(labels)

    # Split data into training and testing sets
    X_train, X_test, y_train, y_test = train_test_split(
        data, labels_ds, test_size=0.2, random_state=42
    )

    # Create LogisticRegression Model
    model = LogisticRegression(
        penalty="l2",
        max_iter=1,  # local epoch
        warm_start=True,  # prevent refreshing weights when fitting
    )
    # Setting initial parameters, akin to model.compile for keras models
    utils.set_initial_params(model)

    local_step = LRImagingLocal()
    params, n_obs, other_results = local_step.fit(model)
    loss_local, n_obs_eval, accuracy, round_num = local_step.evaluate(
        params, round_num=5
    )
    raise ValueError(local_step.evaluate)
