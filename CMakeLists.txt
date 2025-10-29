cmake_minimum_required(VERSION 3.10)
project(st_cam_client CXX)
set(CMAKE_CXX_STANDARD 17)

find_package(PkgConfig REQUIRED)
pkg_check_modules(EFL REQUIRED elementary ewebkit2)
find_library(CURL_LIB curl)
find_library(CJSON_LIB cjson)
find_library(STCLIENT_LIB smartthings-client)

add_executable(st_cam_client main_client.cpp)
target_include_directories(st_cam_client PRIVATE ${EFL_INCLUDE_DIRS})
target_link_libraries(st_cam_client
  ${EFL_LIBRARIES}
  ${CURL_LIB}
  ${CJSON_LIB}
  ${STCLIENT_LIB}
)