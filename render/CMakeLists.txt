cmake_minimum_required(VERSION 3.14)
project(Renderer)

# Specify the C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Find packages
find_package(pybind11 REQUIRED)
find_package(raylib QUIET)

# If raylib not found via config, try pkg-config
if(NOT raylib_FOUND)
    find_package(PkgConfig REQUIRED)
    pkg_check_modules(RAYLIB REQUIRED raylib)
endif()

# Add the module
pybind11_add_module(renderer renderer.cpp)

# Set properties for the module
set_target_properties(renderer PROPERTIES
    CXX_VISIBILITY_PRESET "hidden"
    VISIBILITY_INLINES_HIDDEN ON
)

# Link libraries
if(raylib_FOUND)
    target_link_libraries(renderer PRIVATE raylib)
else()
    target_link_libraries(renderer PRIVATE ${RAYLIB_LIBRARIES})
    target_include_directories(renderer PRIVATE ${RAYLIB_INCLUDE_DIRS})
    target_compile_options(renderer PRIVATE ${RAYLIB_CFLAGS_OTHER})
endif()