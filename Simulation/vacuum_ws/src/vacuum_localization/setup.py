from setuptools import setup

package_name = 'vacuum_localization'

setup(
    name=package_name,
    version='0.5.0',
    packages=[package_name],
    install_requires=['setuptools'],
    zip_safe=True,
    author='Hrishikesh Prasad R',
    description='Stage 5 localization monitoring for Swachh Boudhik Yantra',
    license='MIT',
    entry_points={
        'console_scripts': [
            'localization_monitor = vacuum_localization.localization_monitor:main',
            'recovery_monitor     = vacuum_localization.recovery_monitor:main',
            'localization_metrics = vacuum_localization.localization_metrics:main',
        ],
    },
)
