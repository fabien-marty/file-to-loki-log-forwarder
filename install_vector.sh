#!/bin/bash

set -eu

export VECTOR_VERSION=0.46.1

rm -Rf tmp_vector
mkdir tmp_vector
curl -sSfL https://sh.vector.dev >vector_installer.sh
chmod +x vector_installer.sh
./vector_installer.sh -y --prefix tmp_vector
if [ -d /app/bin ]; then
  # docker mode
  cp -f tmp_vector/bin/vector /app/bin/
else
  # local mode
  cp -f tmp_vector/bin/vector ./bin/vector
fi
rm -Rf tmp_vector
rm -f vector_installer.sh


