# Free5GC Setup & ULCL Traffic Steering

A compact repository for free5GC ULCL (Uplink Classifier) traffic steering implementation guidance across Kubernetes and bare-metal environments.

## What it is

- A documented implementation guide for deploying custom-patched free5GC v3.3.0 on both kubeadm Kubernetes and bare-metal testbed setups.
- Focused on ULCL traffic steering between PSA-UPFs for single and multi-UE topologies.
- Includes step-by-step guidance for cluster setup, Helm deployment, bare-metal validation, and patch debugging.

## Guides

- **Bare metal guide** — implementation and patch notes: https://costasgk.github.io/ulcl-traffic-steering-free5gc/index.html
- **Kubernetes guide** — Helm deployment and cluster setup: https://costasgk.github.io/ulcl-traffic-steering-free5gc/k8s-guide.html

## Bare-Metal Cold Start GUI

`app.py` is a Python GUI tool for automating the cold-start sequence of the bare-metal MARE testbed. It SSH's into the remote VMs in the correct order and brings up all 5G components without manual intervention.

**Startup order:** I-UPF → PSA-UPF → PSA-UPF-B → free5GC Core → gNB → UE

**Usage:**

```bash
pip install -r requirements.txt

python app.py
```

Fill in the VM IPs, credentials, and UE count in the GUI, then click **Start Testbed**. A terminal window opens for each service showing live output. The password is typed automatically — no manual sudo prompts.

