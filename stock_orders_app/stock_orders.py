import threading
import random
import time
from concurrent.futures import ThreadPoolExecutor

# Order types
BUY = 0
SELL = 1

# Company names for tickers
COMPANY_NAMES = [
    "Apple", "Microsoft", "Amazon", "Alphabet", "Meta", "Tesla", "Nvidia", "Berkshire",
    "JPMorgan", "Johnson&Johnson", "Visa", "Walmart", "Procter&Gamble", "Mastercard", "Exxon",
    "UnitedHealth", "HomeDepot", "BankOfAmerica", "Verizon", "Chevron", "Pfizer", "Intel",
    "Disney", "Coca-Cola", "Netflix", "Adobe", "Cisco", "Pepsi", "Oracle", "Comcast", "PayPal",
    "Salesforce"
]
# Extend to 1024 companies by adding numbered variations
for i in range(len(COMPANY_NAMES), 1024):
    base_name = COMPANY_NAMES[i % len(COMPANY_NAMES)]
    COMPANY_NAMES.append(f"{base_name}-{i//len(COMPANY_NAMES)}")

class StockTradingEngine:
    def __init__(self, num_tickers=1024, max_orders=10000):
        self.num_tickers = num_tickers
        self.max_orders = max_orders
        
        # Arrays to hold orders
        self.order_types = [-1] * max_orders  # -1 indicates empty slot
        self.order_tickers = [0] * max_orders
        self.order_quantities = [0] * max_orders
        self.order_prices = [0.0] * max_orders
        
        # Index tracking
        self.next_order_id = 0
        self.active_orders = [[] for _ in range(num_tickers)]  # Lists of order IDs per ticker
        
        # Locks and processing
        self.locks = [threading.Lock() for _ in range(num_tickers)]
        self.order_lock = threading.Lock()
        self.ticker_queue = []
        self.queue_lock = threading.Lock()
        self.is_running = True
        
        # Transaction history
        self.transactions = []
        self.transaction_lock = threading.Lock()
        
        # Start matching thread
        self.matcher_thread = threading.Thread(target=self._match_processor)
        self.matcher_thread.daemon = True
        self.matcher_thread.start()

    def addOrder(self, order_type, ticker, quantity, price, trader_id=None):
        """
        Add a new order to the order book
        
        Args:
            order_type: BUY (0) or SELL (1)
            ticker: Integer representing stock ticker (0-1023)
            quantity: Number of shares
            price: Price per share
            trader_id: Optional identifier for the trader
            
        Returns:
            order_id: Unique identifier for the order
        """
        if not 0 <= ticker < self.num_tickers:
            raise ValueError(f"Ticker must be between 0 and {self.num_tickers-1}")
        
        # Getting next available order ID
        with self.order_lock:
            order_id = self.next_order_id
            self.next_order_id = (self.next_order_id + 1) % self.max_orders
            
            # If we're overwriting an existing order, make sure it's not active
            if self.order_types[order_id] != -1:
                old_ticker = self.order_tickers[order_id]
                with self.locks[old_ticker]:
                    if order_id in self.active_orders[old_ticker]:
                        self.active_orders[old_ticker].remove(order_id)
            
            # Storing the order details in arrays
            self.order_types[order_id] = order_type
            self.order_tickers[order_id] = ticker
            self.order_quantities[order_id] = quantity
            self.order_prices[order_id] = price
        
        # Adding to active orders for this ticker with lock
        with self.locks[ticker]:
            self.active_orders[ticker].append(order_id)
        
        # Queuing ticker for matching if not already queued
        with self.queue_lock:
            if ticker not in self.ticker_queue:
                self.ticker_queue.append(ticker)
        
        order_name = "BUY" if order_type == BUY else "SELL"
        trader_info = f" by trader {trader_id}" if trader_id else ""
        print(f"Order #{order_id}: {order_name} {quantity} shares of {COMPANY_NAMES[ticker]} at ${price:.2f}{trader_info}")
        
        return order_id

    def _match_processor(self):
        """Background thread to process matching queue"""
        while self.is_running:
            ticker = None
            with self.queue_lock:
                if self.ticker_queue:
                    ticker = self.ticker_queue.pop(0)
            
            if ticker is not None:
                self.matchOrders(ticker)
            else:
                time.sleep(0.01)  # Sleep if no tickers to process

    def matchOrders(self, ticker):
        """
        Match buy and sell orders for a specific ticker
        
        Args:
            ticker: Integer representing stock ticker (0-1023)
        """
        with self.locks[ticker]:
            order_ids = self.active_orders[ticker]
            
            if not order_ids:
                return  # No orders to match
            
            # Separating buy and sell orders
            buy_orders = []
            sell_orders = []
            
            for order_id in order_ids:
                if self.order_types[order_id] == BUY:
                    buy_orders.append(order_id)
                else:
                    sell_orders.append(order_id)
            
            if not buy_orders or not sell_orders:
                return  # Nothing to match
            
            # Tracking which orders to remove
            orders_to_remove = set()
            
            # Processing all possible matches with O(n) time complexity
            for buy_id in buy_orders:
                if buy_id in orders_to_remove or self.order_quantities[buy_id] <= 0:
                    continue
                
                buy_price = self.order_prices[buy_id]
                
                # Finding the best matching sell order (lowest price that meets criteria)
                best_sell_id = None
                best_sell_price = float('inf')
                
                for sell_id in sell_orders:
                    if sell_id in orders_to_remove or self.order_quantities[sell_id] <= 0:
                        continue
                    
                    sell_price = self.order_prices[sell_id]
                    
                    if buy_price >= sell_price and sell_price < best_sell_price:
                        best_sell_id = sell_id
                        best_sell_price = sell_price
                
                # If we found a match, execute the trade
                if best_sell_id is not None:
                    buy_qty = self.order_quantities[buy_id]
                    sell_qty = self.order_quantities[best_sell_id]
                    
                    # Determining the trade quantity
                    trade_qty = min(buy_qty, sell_qty)
                    executed_price = best_sell_price
                    
                    # Updating the remaining quantities
                    self.order_quantities[buy_id] -= trade_qty
                    self.order_quantities[best_sell_id] -= trade_qty
                    
                    # Recording the transaction
                    transaction = {
                        'ticker': ticker,
                        'company': COMPANY_NAMES[ticker],
                        'quantity': trade_qty,
                        'price': executed_price,
                        'buy_order_id': buy_id,
                        'sell_order_id': best_sell_id,
                        'timestamp': time.time()
                    }
                    
                    with self.transaction_lock:
                        self.transactions.append(transaction)
                    
                    # Printing the trade execution
                    print(f"MATCH EXECUTED: Order #{buy_id} (BUY) matched with Order #{best_sell_id} (SELL)")
                    print(f"  {trade_qty} shares of {COMPANY_NAMES[ticker]} traded at ${executed_price:.2f}")
                    print(f"  Value: ${trade_qty * executed_price:.2f}")
                    
                    # Marking orders for removal if quantity is 0
                    if self.order_quantities[buy_id] == 0:
                        orders_to_remove.add(buy_id)
                    
                    if self.order_quantities[best_sell_id] == 0:
                        orders_to_remove.add(best_sell_id)
            
            # Removing the completed orders from active orders
            self.active_orders[ticker] = [order_id for order_id in order_ids 
                                         if order_id not in orders_to_remove]
            
            # If there are still potential matches, queue the ticker again
            if any(self.order_types[order_id] == BUY for order_id in self.active_orders[ticker]) and \
               any(self.order_types[order_id] == SELL for order_id in self.active_orders[ticker]):
                with self.queue_lock:
                    if ticker not in self.ticker_queue:
                        self.ticker_queue.append(ticker)

    def print_order_book(self, ticker):
        """Print the current order book for a given ticker"""
        if not 0 <= ticker < self.num_tickers:
            print(f"Invalid ticker: {ticker}")
            return
            
        print(f"\nOrder Book for {COMPANY_NAMES[ticker]}:")
        print("-" * 60)
        
        with self.locks[ticker]:
            buy_orders = []
            sell_orders = []
            
            for order_id in self.active_orders[ticker]:
                if self.order_types[order_id] == BUY:
                    buy_orders.append((order_id, self.order_quantities[order_id], self.order_prices[order_id]))
                else:
                    sell_orders.append((order_id, self.order_quantities[order_id], self.order_prices[order_id]))
            
            print("BUY ORDERS:")
            if buy_orders:
                # Sorting the buy orders by price (highest first)
                buy_orders.sort(key=lambda x: x[2], reverse=True)
                for order_id, qty, price in buy_orders:
                    print(f"  Order #{order_id}: {qty} shares at ${price:.2f}")
            else:
                print("  No buy orders")
                
            print("\nSELL ORDERS:")
            if sell_orders:
                # Sorting the sell orders by price (lowest first)
                sell_orders.sort(key=lambda x: x[2])
                for order_id, qty, price in sell_orders:
                    print(f"  Order #{order_id}: {qty} shares at ${price:.2f}")
            else:
                print("  No sell orders")
        
        print("-" * 60)

    def print_transaction_summary(self):
        """Print a summary of all completed transactions"""
        with self.transaction_lock:
            if not self.transactions:
                print("\nNo transactions completed yet.")
                return
                
            total_value = sum(t['quantity'] * t['price'] for t in self.transactions)
            total_shares = sum(t['quantity'] for t in self.transactions)
            
            print("\nTransaction Summary:")
            print("-" * 80)
            print(f"Total Transactions: {len(self.transactions)}")
            print(f"Total Shares Traded: {total_shares}")
            print(f"Total Trading Value: ${total_value:.2f}")
            
            # Grouping by company
            company_stats = {}
            for t in self.transactions:
                company = t['company']
                if company not in company_stats:
                    company_stats[company] = {
                        'trades': 0,
                        'shares': 0,
                        'value': 0.0
                    }
                company_stats[company]['trades'] += 1
                company_stats[company]['shares'] += t['quantity']
                company_stats[company]['value'] += t['quantity'] * t['price']
            
            print("\nTrading by Company:")
            for company, stats in sorted(company_stats.items(), key=lambda x: x[1]['value'], reverse=True):
                print(f"  {company}: {stats['trades']} trades, {stats['shares']} shares, ${stats['value']:.2f}")
            
            print("-" * 80)
            
            # Listing the recent transactions
            print("\nRecent Transactions:")
            for t in sorted(self.transactions[-10:], key=lambda x: x['timestamp'], reverse=True):
                print(f"  {t['company']}: {t['quantity']} shares at ${t['price']:.2f} (${t['quantity'] * t['price']:.2f})")

    def shutdown(self):
        """Shutdown the trading engine"""
        self.is_running = False
        self.matcher_thread.join()
        self.print_transaction_summary()

# Simulation of trading activity
def simulate_trading(engine, num_orders=1000, max_threads=10, trading_time=5):
    # Selecting a subset of tickers for more realistic simulation
    active_tickers = list(range(30))  # Using the first 30 companies
    traders = [f"Trader-{i}" for i in range(20)]
    
    print(f"\nStarting trading simulation with {len(active_tickers)} active stocks...")
    print(f"Simulating {num_orders} orders over {trading_time} seconds with {max_threads} concurrent traders")
    print("-" * 80)
    
    start_time = time.time()
    order_count = 0
    
    def random_order():
        nonlocal order_count
        if order_count >= num_orders or time.time() - start_time >= trading_time:
            return
            
        order_count += 1
        
        # More realistic order generation
        order_type = random.choice([BUY, SELL])
        ticker = random.choice(active_tickers)
        
        # More realistic quantities (round lots)
        quantity = random.choice([100, 200, 500, 1000, 2000, 5000])
        
        # More realistic pricing
        base_price = 10 + (ticker % 10) * 10  # Base price varies by ticker
        variation = random.uniform(-0.5, 0.5)  # Price variation
        price = round(base_price + variation, 2)
        
        trader = random.choice(traders)
        
        try:
            engine.addOrder(order_type, ticker, quantity, price, trader)
        except Exception as e:
            print(f"Error adding order: {e}")
        
        # Scheduling the next order
        if order_count < num_orders and time.time() - start_time < trading_time:
            delay = random.uniform(0.01, 0.05)  # Randomly delaying between the orders
            threading.Timer(delay, random_order).start()
    
    # Starting multiple traders
    for _ in range(max_threads):
        random_order()
    
    # Running it for specified duration
    time.sleep(trading_time + 1)  # Allowing an extra time for final matches
    
    # Showing the final order books for a few companies
    for ticker in random.sample(active_tickers, min(5, len(active_tickers))):
        engine.print_order_book(ticker)
    
    # Shutdown engine
    engine.shutdown()
    print("\nTrading simulation completed.")

# Running a simulation
if __name__ == "__main__":
    engine = StockTradingEngine()
    simulate_trading(engine, num_orders=200, trading_time=3)