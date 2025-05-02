cmake_minimum_required(VERSION 3.14)
project(Renderer)

# Specify the C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Set the SFML directory (update the path to where SFML is installed on your system)
set(SFML_DIR "/usr/local/Cellar/sfml/2.5.1/lib/cmake/SFML")

# Find pybind11 and SFML
find_package(pybind11 REQUIRED)
find_package(raylib CONFIG REQUIRED)

# Add the module
pybind11_add_module(renderer renderer.cpp)

# Link SFML libraries
target_link_libraries(renderer PRIVATE raylib)