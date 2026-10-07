FROM astrocrpublic.azurecr.io/runtime:3.3-8-python-3.12

# Local WSL bind mounts belong to UID 1000. Airflow requires a named user;
# keep Astro's build user and add a separate account for the mounted runtime.
USER root
RUN useradd --uid 1000 --gid 0 --home-dir /home/wsl_airflow \
    --create-home --shell /bin/bash wsl_airflow
USER astro
