FROM rabbitmq:3.13-management

ENV DELAYED_PLUGIN_VERSION=3.13.0

# Install curl (or you could install wget instead)
RUN apt-get update && apt-get install -y curl \
    && curl -L -o /plugins/rabbitmq_delayed_message_exchange-${DELAYED_PLUGIN_VERSION}.ez \
       https://github.com/rabbitmq/rabbitmq-delayed-message-exchange/releases/download/v${DELAYED_PLUGIN_VERSION}/rabbitmq_delayed_message_exchange-${DELAYED_PLUGIN_VERSION}.ez \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy enabled_plugins file to enable delayed exchange + management plugin
COPY enabled_plugins /etc/rabbitmq/enabled_plugins
