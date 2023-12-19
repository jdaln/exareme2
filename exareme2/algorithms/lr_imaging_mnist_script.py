from exareme2.algorithms.imaging_fed_average import aggregate_evaluate
from exareme2.algorithms.lr_imaging_mnist_global import LRImagingGlobal
from exareme2.algorithms.lr_imaging_mnist_local import LRImagingLocal

data_locations = [
    "exareme2/imaging_data/MNIST/node1",
    "exareme2/imaging_data/MNIST/node2",
]


def RunDrill(data_locations):
    round = 0  # Loop condition

    while round < 5:
        # Some initial data

        data_location_node1 = data_locations[0]
        data_location_node2 = data_locations[1]

        # Process data in the local class
        result_node1 = LRImagingLocal(data_location_node1)
        result_node2 = LRImagingLocal(data_location_node2)

        local_results = {"result_node1": result_node1, "result_node2": result_node2}

        # Conditionally continue the loop based on the result
        if result_node1 and result_node2:
            # Process data in the second class
            result_global = LRImagingGlobal()
            aggregates = result_global.calculate_aggregates(round, local_results)

            # Modify the condition based on the result

        else:
            # Exit the loop if the condition is not met
            condition = False
            raise ValueError("No data from local nodes")

        round += 1

    print("Loop completed.")


if __name__ == "__main__":
    RunDrill(data_locations)


# import os
# import random
# import shutil
# from glob import glob
#
# def split_files(input_folder, output_folder1, output_folder2, split_ratio=0.5):
#     # Ensure output folders exist
#     os.makedirs(output_folder1, exist_ok=True)
#     os.makedirs(output_folder2, exist_ok=True)
#
#     # Iterate over the subdirectories in the input folder
#     for subdirectory in os.listdir(input_folder):
#         subdirectory_path = os.path.join(input_folder, subdirectory)
#
#         # Skip if it's not a directory
#         if not os.path.isdir(subdirectory_path):
#             continue
#
#         # Retrieve the list of files in the current subdirectory
#         files = [os.path.basename(file) for file in glob(os.path.join(subdirectory_path, '*'))]
#
#         # Skip if there are no files in the subdirectory
#         if not files:
#             continue
#
#         # Shuffle the list of files in the current subdirectory
#         random.shuffle(files)
#
#         # Calculate the split index based on the split ratio
#         split_index = int(len(files) * split_ratio)
#
#         # Split the files into two parts
#         part1_files = files[:split_index]
#         part2_files = files[split_index:]
#
#         # Create subdirectories in the output folders to maintain structure
#         output_subdir1 = os.path.join(output_folder1, subdirectory)
#         output_subdir2 = os.path.join(output_folder2, subdirectory)
#
#         # Create subdirectories if they don't exist
#         os.makedirs(output_subdir1, exist_ok=True)
#         os.makedirs(output_subdir2, exist_ok=True)
#
#         # Copy files to output folders while maintaining subdirectory structure
#         copy_files(subdirectory_path, output_subdir1, part1_files)
#         copy_files(subdirectory_path, output_subdir2, part2_files)
#
# def copy_files(source_folder, destination_folder, file_list):
#     for filename in file_list:
#         source_path = os.path.join(source_folder, filename)
#         destination_path = os.path.join(destination_folder, filename)
#         shutil.copy2(source_path, destination_path)
#
# if __name__ == "__main__":
#     input_folder = "exareme2/imaging_data/MNIST/training"
#     output_folder1 = "exareme2/imaging_data/MNIST/node1"
#     output_folder2 = "exareme2/imaging_data/MNIST/node2"
#     split_ratio = 0.5  # Adjust this ratio as needed
#
#     split_files(input_folder, output_folder1, output_folder2, split_ratio)
