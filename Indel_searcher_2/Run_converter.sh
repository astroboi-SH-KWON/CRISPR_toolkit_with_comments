#!/bin/bash


####################
## User parameter ##
####################################

user=JaeWoo
project=JaeWoo_test_samples


####################################





while read python_path;do
    python=$python_path
done < ../PythonPath.txt

nohup $python ./BaseEdit_input_converter.py $user $project > ./Output/${user}/${project}/Log/Converter_log.txt 2>&1 &
