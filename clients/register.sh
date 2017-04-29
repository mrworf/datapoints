#!/bin/bash
#
# Registers or lists registered sources on your server
#
#
SERVER=$1
NAME=$2
TYPE=$3
ACCURACY=$4
PARAMS=$5

PRETTY=cat
if hash jq ; then
  # Make it more pretty
  PRETTY=jq
fi

if [ -z "${SERVER}" ]; then
  echo "Usage: $0 <server> [<name> <type> [<accuracy> [<params>]]]"
  exit 255
fi

if [ -z "${NAME}" ]; then
  curl -X GET http://${SERVER}:8088/source | ${PRETTY}
  exit $?
fi

REGISTER="{\"name\":\"${NAME}\",\"type\":${TYPE}"

if [ ! -z "${ACCURACY}" ]; then
  REGISTER="${REGISTER},\"accuracy\":${ACCURACY}"
fi
if [ ! -z "${PARAMS}" ]; then
  REGISTER="${REGISTER},\"parameters\":\"${PARAMS}\""
fi
REGISTER="${REGISTER}}"

CONTENT="$(curl 2>/dev/null -H "Content-Type: application/json" -X POST -d "${REGISTER}" http://${SERVER}:8088/register)"
ERR=$?
UUID="$(echo "${CONTENT}" | jq .data.uuid)"
if [ -z "${UUID}" -o "${UUID}" = "null" ] ; then
  echo "Failed to register:"
  echo "${CONTENT}" | ${PRETTY}
else
  echo "UUID to use: ${UUID}"
fi
exit $ERR