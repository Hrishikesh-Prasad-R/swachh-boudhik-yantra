from setuptools import setup

package_name = 'vacuum_exploration'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Hrishikesh-Prasad-R',
    maintainer_email='rprasadhrishikesh@gmail.com',
    description='Stage 4B: Autonomous Frontier Exploration for Swachh Boudhik Yantra',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'frontier_detector   = vacuum_exploration.frontier_detector:main',
            'exploration_manager = vacuum_exploration.exploration_manager:main',
            'frontier_visualizer = vacuum_exploration.frontier_visualizer:main',
            'exploration_metrics = vacuum_exploration.exploration_metrics:main',
        ],
    },
)
