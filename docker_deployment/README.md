# BrachyD2ccEval Docker Deployment

This folder contains the necessary files to build and run the BrachyD2ccEval application in a Docker container.

## Files

- `Dockerfile`: This file defines the steps to create a Docker image for the application. It clones the repository, installs dependencies, and sets up the environment to run the Streamlit app.
- `docker-compose.yml`: This file is used to manage the Docker container. It defines the `app` service, builds the image from the `Dockerfile`, maps the necessary ports, and configures the network.

## Usage

To build and run the application, navigate to this directory in a terminal and run the following command:

```bash
docker-compose up -d
```

This will start the application in detached mode. You can then access the Streamlit GUI by navigating to `http://<host-ip>:8501` in your web browser.

## Networking

The `docker-compose.yml` file is configured to use a custom bridge network named `brachynet` that attaches to the `br0` interface on the host machine. It is configured to use the `172.30.98.0/24` subnet. You may need to adjust the `ipv4_address` in the `docker-compose.yml` file to a static IP assigned to you within that subnet.
